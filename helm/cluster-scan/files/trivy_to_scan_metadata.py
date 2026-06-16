#!/usr/bin/env python3
"""Convert one Trivy JSON report into the compact scan metadata contract.

Trivy can already emit raw JSON with `trivy image --format json`. This adapter turns
that raw report into the smaller `scan-metadata/v1` record consumed by the refresh
planner.

The scanner workflow should provide lineage/routing fields such as base family and
managed-base status from labels, scanner enrichment, or an external inventory map.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .filter_trivy_actionable import best_fixed_version, classify_target_class
except ImportError:  # pragma: no cover - direct script execution
    from filter_trivy_actionable import best_fixed_version, classify_target_class

HIGH_CRITICAL = {"CRITICAL", "HIGH"}


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _deep_clean(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            v2 = _deep_clean(v)
            if v2 in (None, "", [], {}):
                continue
            out[k] = v2
        return out
    if isinstance(value, list):
        cleaned = [_deep_clean(v) for v in value]
        return [v for v in cleaned if v not in (None, "", [], {})]
    return _clean(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def count_findings(report: dict[str, Any]) -> dict[str, Any]:
    critical = 0
    high = 0
    fixable_critical = 0
    fixable_high = 0
    target_classes: list[str] = []

    for result in report.get("Results") or []:
        target_class = classify_target_class(result)
        if target_class not in target_classes:
            target_classes.append(target_class)
        for vuln in result.get("Vulnerabilities") or []:
            severity = (_clean(vuln.get("Severity")) or "").upper()
            if severity not in HIGH_CRITICAL:
                continue
            fixed = best_fixed_version(vuln)
            if severity == "CRITICAL":
                critical += 1
                if fixed:
                    fixable_critical += 1
            elif severity == "HIGH":
                high += 1
                if fixed:
                    fixable_high += 1

    return {
        "criticalCount": critical,
        "highCount": high,
        "fixableCriticalCount": fixable_critical,
        "fixableHighCount": fixable_high,
        "targetClasses": sorted(target_classes),
    }


def build_record(args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    counts = count_findings(report)
    image = _clean(args.image) or _clean(report.get("ArtifactName"))
    scan_timestamp = _clean(args.scan_timestamp) or _clean(report.get("CreatedAt")) or utc_now()

    base_image = None
    if args.base_image or args.base_digest or args.base_family:
        base_image = {
            "image": _clean(args.base_image),
            "digest": _clean(args.base_digest),
            "family": _clean(args.base_family),
            "source": _clean(args.base_source) or "scanner-lineage",
        }

    return _deep_clean(
        {
            "schemaVersion": "scan-metadata/v1",
            "image": image,
            "digest": _clean(args.digest),
            "normalizedReference": _clean(args.normalized_reference),
            "normalizedImageName": _clean(args.normalized_image_name),
            "canonicalKey": _clean(args.canonical_key),
            "scanner": _clean(args.scanner),
            "scannerVersion": _clean(args.scanner_version),
            "scanTimestamp": scan_timestamp,
            "baseFamily": _clean(args.base_family),
            "baseImage": base_image,
            "managedBaseImage": args.managed_base_image,
            "targetClasses": counts["targetClasses"],
            "criticalCount": counts["criticalCount"],
            "highCount": counts["highCount"],
            "fixableCriticalCount": counts["fixableCriticalCount"],
            "fixableHighCount": counts["fixableHighCount"],
            "summaryPath": _clean(args.summary_path),
            "reportPath": _clean(args.report_path),
            "rawReportPath": _clean(args.raw_report_path),
            "scanRunId": _clean(args.scan_run_id),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trivy_json", help="Path to raw Trivy JSON report")
    parser.add_argument("output", help="Path to write scan metadata JSON array")
    parser.add_argument("--image", help="Image ref scanned. Defaults to Trivy ArtifactName")
    parser.add_argument("--digest", help="Image digest when known")
    parser.add_argument("--normalized-reference")
    parser.add_argument("--normalized-image-name")
    parser.add_argument("--canonical-key")
    parser.add_argument("--scanner", default="trivy")
    parser.add_argument("--scanner-version")
    parser.add_argument("--scan-timestamp", help="UTC ISO-8601 timestamp. Defaults to report CreatedAt or now")
    parser.add_argument("--base-family")
    parser.add_argument("--base-image")
    parser.add_argument("--base-digest")
    parser.add_argument("--base-source", default="scanner-lineage")
    parser.add_argument("--managed-base-image", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--summary-path")
    parser.add_argument("--report-path")
    parser.add_argument("--raw-report-path")
    parser.add_argument("--scan-run-id")
    args = parser.parse_args()

    report = json.loads(Path(args.trivy_json).read_text())
    if not isinstance(report, dict):
        raise SystemExit("Trivy report must be a JSON object")

    record = build_record(args, report)
    Path(args.output).write_text(json.dumps([record], indent=2) + "\n")


if __name__ == "__main__":
    main()
