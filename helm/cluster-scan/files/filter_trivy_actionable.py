#!/usr/bin/env python3
"""Filter Trivy JSON into remediation-oriented findings.

Purpose in the system:
- This script sits between raw scanning and remediation.
- Trivy emits a lot of vulnerability data, but remediation needs a smaller, structured payload.

Why this is needed:
- Not every High/Critical finding is actionable.
- We only want findings that have enough information to choose a strategy and attempt a fix.

How it plugs in:
- The scan WorkflowTemplate runs Trivy first.
- It then calls this script to:
  1. keep only policy-relevant severities,
  2. classify the affected target into a remediation family,
  3. mark each finding actionable or non-actionable,
  4. emit JSON that later gating / remediation logic can consume.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_SEVERITIES = {"CRITICAL", "HIGH"}


def _clean(value: Any) -> Any:
    """Normalize empty strings to None so downstream logic is less annoying."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def classify_target_class(result: dict[str, Any]) -> str:
    """Map a Trivy result section to a remediation strategy family.

    Why this exists:
    - The same scanner report may include Python deps, Java deps, OS packages, and other junk.
    - Remediation is not one-size-fits-all; it needs a coarse target family first.

    How it plugs in:
    - The returned class is attached to each finding.
    - The future remediation worker can branch on this value to select the correct fixer.
    """
    target = (_clean(result.get("Target")) or "").lower()
    result_class = (_clean(result.get("Class")) or "").lower()
    result_type = (_clean(result.get("Type")) or "").lower()

    if result_class == "lang-pkgs":
        if "python" in target or "requirements" in target or "poetry.lock" in target or "pip" in target:
            return "python"
        if any(x in target for x in ["pom.xml", "maven", "gradle", "jar", "java"]):
            return "java"
        return "language-package"

    if result_class == "os-pkgs":
        if "nginx" in target:
            return "nginx"
        if any(x in result_type for x in ["rpm", "redhat", "rhel"]):
            return "rhel-base"
        return "os-package"

    if "nginx" in target:
        return "nginx"
    if any(x in target for x in ["python", "requirements", "poetry.lock", "pip"]):
        return "python"
    if any(x in target for x in ["pom.xml", "maven", "gradle", "jar", "java"]):
        return "java"
    return "unknown"


def best_fixed_version(vulnerability: dict[str, Any]) -> str | None:
    """Pick the best available fix version field from the Trivy record."""
    fixed = _clean(vulnerability.get("FixedVersion"))
    if fixed:
        return fixed

    data_source = vulnerability.get("DataSource") or {}
    return _clean(data_source.get("FixedVersion"))


def actionability_reason(vulnerability: dict[str, Any], target_class: str) -> tuple[bool, str]:
    """Decide whether a finding is safe to hand to remediation automation.

    A finding is non-actionable if:
    - the package name is missing,
    - no fixed version is known,
    - or we cannot classify the target well enough to choose a strategy.
    """
    pkg = _clean(vulnerability.get("PkgName"))
    fixed = best_fixed_version(vulnerability)

    if not pkg:
        return False, "missing-package-name"
    if not fixed:
        return False, "no-fixed-version"
    if target_class == "unknown":
        return False, "unknown-target-class"
    return True, "fixed-version-available"


def flatten_findings(trivy_report: dict[str, Any], allowed_severities: set[str]) -> list[dict[str, Any]]:
    """Flatten Trivy's nested result structure into one record per relevant finding.

    Why this exists:
    - Trivy groups vulnerabilities by target file/layer/result section.
    - The orchestrator/remediation side wants a simpler list of findings with enough metadata
      attached to each item.
    """
    actionable_findings = []
    for result in trivy_report.get("Results") or []:
        target_class = classify_target_class(result)
        for vuln in result.get("Vulnerabilities") or []:
            severity = (_clean(vuln.get("Severity")) or "").upper()
            if severity not in allowed_severities:
                continue

            actionable, reason = actionability_reason(vuln, target_class)
            record = {
                "vulnerabilityId": _clean(vuln.get("VulnerabilityID")),
                "pkgName": _clean(vuln.get("PkgName")),
                "installedVersion": _clean(vuln.get("InstalledVersion")),
                "fixedVersion": best_fixed_version(vuln),
                "severity": severity,
                "title": _clean(vuln.get("Title")),
                "primaryUrl": _clean(vuln.get("PrimaryURL")),
                "target": _clean(result.get("Target")),
                "class": _clean(result.get("Class")),
                "type": _clean(result.get("Type")),
                "targetClass": target_class,
                "actionable": actionable,
                "actionabilityReason": reason,
            }
            actionable_findings.append(record)
    return actionable_findings


def summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a compact summary for reporting and quick workflow checks."""
    summary = {
        "totalHighOrCritical": len(findings),
        "actionableCount": 0,
        "nonActionableCount": 0,
        "bySeverity": {},
        "byTargetClass": {},
        "nonActionableReasons": {},
    }

    by_severity: dict[str, int] = {}
    by_target_class: dict[str, int] = {}
    non_actionable_reasons: dict[str, int] = {}

    for finding in findings:
        sev = finding["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1
        tgt = finding["targetClass"]
        by_target_class[tgt] = by_target_class.get(tgt, 0) + 1
        if finding["actionable"]:
            summary["actionableCount"] += 1
        else:
            summary["nonActionableCount"] += 1
            reason = finding["actionabilityReason"]
            non_actionable_reasons[reason] = non_actionable_reasons.get(reason, 0) + 1

    summary["bySeverity"] = dict(sorted(by_severity.items()))
    summary["byTargetClass"] = dict(sorted(by_target_class.items()))
    summary["nonActionableReasons"] = dict(sorted(non_actionable_reasons.items()))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to trivy JSON output")
    parser.add_argument("output_dir", help="Directory for filtered outputs")
    parser.add_argument("--severities", default="CRITICAL,HIGH", help="Comma-separated severities to keep")
    args = parser.parse_args()

    allowed = {s.strip().upper() for s in args.severities.split(",") if s.strip()} or DEFAULT_SEVERITIES
    report = json.loads(Path(args.input).read_text())

    # Convert raw scanner data into remediation-friendly outputs.
    findings = flatten_findings(report, allowed)
    summary = summarize(findings)

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "actionable-findings.json").write_text(json.dumps(findings, indent=2))
    (outdir / "actionable-findings.min.json").write_text(json.dumps(findings, separators=(",", ":")))
    (outdir / "actionable-summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
