#!/usr/bin/env python3
"""Plan internal base-family refresh work from existing scan metadata.

Purpose in the system:
- Consume the existing scanner's metadata outputs instead of re-archiving/scanning every image again.
- Convert vulnerable runtime image observations into deduplicated internal base-family refresh plans.

Why this is needed:
- The current scanning platform already knows which running images are vulnerable.
- The remediation platform should reuse that signal, not duplicate storage by hauling full image archives around.
- Multiple vulnerable app images often collapse to one internal base family that needs refreshing once.

How it plugs in:
- Input A: unique image records from the dedupe phase.
- Input B: compact scan metadata emitted by the existing Aqua/Trivy pipeline.
- Input C: internal base-family catalog with upstream image + customization + publish targets.
- Output: refresh plans for the Argo family-refresh child workflow.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BASE_REMEDIATION_CLASSES = {
    "rhel-base",
    "os-package",
    "nginx",
    "java-runtime",
    "jdk-runtime",
    "python-runtime",
}


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


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


def build_metadata_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index scan metadata by the most useful lookup keys we can find."""
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        for key in [
            _clean(record.get("digest")),
            _clean(record.get("image")),
            _clean(record.get("normalizedReference")),
            _clean(record.get("normalizedImageName")),
            _clean(record.get("canonicalKey")),
        ]:
            if key:
                index[key] = record
    return index


def match_family(image_record: dict[str, Any], metadata_record: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve an impacted image to the managed internal base family that should be rebuilt."""
    explicit_family = _clean(metadata_record.get("baseFamily")) or _clean(image_record.get("baseFamily"))
    families = catalog.get("families") or []
    if explicit_family:
        for family in families:
            if family.get("name") == explicit_family:
                return family

    image_name = _clean(image_record.get("normalizedImageName") or image_record.get("image")) or ""
    for family in families:
        selectors = family.get("selectors") or {}
        for prefix in selectors.get("repositoryPrefixes") or []:
            if image_name.startswith(prefix):
                return family
        for regex in selectors.get("imageRegexes") or []:
            if re.search(regex, image_name):
                return family
    return None


def metadata_lookup_keys(image_record: dict[str, Any]) -> list[str]:
    return [
        _clean(image_record.get("digest")),
        _clean(image_record.get("image")),
        _clean(image_record.get("normalizedImageName")),
        _clean(image_record.get("canonicalKey")),
    ]


def summarize_severity(metadata_record: dict[str, Any]) -> dict[str, int]:
    summary = metadata_record.get("summary") or {}
    return {
        "critical": _int(summary.get("criticalCount", metadata_record.get("criticalCount"))),
        "high": _int(summary.get("highCount", metadata_record.get("highCount"))),
        "fixableCritical": _int(summary.get("fixableCriticalCount", metadata_record.get("fixableCriticalCount"))),
        "fixableHigh": _int(summary.get("fixableHighCount", metadata_record.get("fixableHighCount"))),
    }


def target_classes(metadata_record: dict[str, Any]) -> list[str]:
    classes = []
    for value in _ensure_list(metadata_record.get("targetClasses") or metadata_record.get("targetClass")):
        cleaned = _clean(value)
        if cleaned:
            classes.append(cleaned)
    return classes


def recommend_refresh(image_record: dict[str, Any], metadata_record: dict[str, Any], family: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    sev = summarize_severity(metadata_record)
    classes = set(target_classes(metadata_record))
    managed_base = metadata_record.get("managedBaseImage")

    if sev["critical"] <= 0 and sev["high"] <= 0:
        reasons.append("no-high-or-critical-findings")
        return False, reasons

    if sev["fixableCritical"] <= 0 and sev["fixableHigh"] <= 0:
        reasons.append("no-fixable-high-or-critical-findings")
        return False, reasons

    if not classes.intersection(BASE_REMEDIATION_CLASSES):
        reasons.append("findings-do-not-look-like-base-runtime-issues")
        return False, reasons

    if managed_base is False:
        reasons.append("scanner-marked-image-as-non-managed-base")
        return False, reasons

    if not family:
        reasons.append("no-base-family-match-found")
        return False, reasons

    reasons.extend([
        "fixable-high-or-critical-finding-present",
        "base-runtime-target-class-present",
        f"matched-family:{family.get('name')}",
    ])
    return True, reasons


def build_evaluations(unique_images: list[dict[str, Any]], metadata_index: dict[str, dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for image_record in unique_images:
        metadata_record = None
        for key in metadata_lookup_keys(image_record):
            if key and key in metadata_index:
                metadata_record = metadata_index[key]
                break

        if not metadata_record:
            evaluations.append(
                {
                    "image": image_record.get("image"),
                    "canonicalKey": image_record.get("canonicalKey"),
                    "matchedScanMetadata": False,
                    "refreshRecommended": False,
                    "reasons": ["no-scan-metadata-match-found"],
                }
            )
            continue

        family = match_family(image_record, metadata_record, catalog)
        should_refresh, reasons = recommend_refresh(image_record, metadata_record, family)
        sev = summarize_severity(metadata_record)
        evaluation = {
            "image": image_record.get("image"),
            "canonicalKey": image_record.get("canonicalKey"),
            "matchedScanMetadata": True,
            "scanMetadataReference": {
                "scanner": _clean(metadata_record.get("scanner")),
                "scannerVersion": _clean(metadata_record.get("scannerVersion")),
                "scanTimestamp": _clean(metadata_record.get("scanTimestamp")),
                "summaryPath": _clean(metadata_record.get("summaryPath")),
                "reportPath": _clean(metadata_record.get("reportPath")),
                "rawReportPath": _clean(metadata_record.get("rawReportPath")),
                "scanRunId": _clean(metadata_record.get("scanRunId")),
            },
            "severity": sev,
            "targetClasses": target_classes(metadata_record),
            "managedBaseImage": metadata_record.get("managedBaseImage"),
            "baseFamily": family.get("name") if family else _clean(metadata_record.get("baseFamily")),
            "baseImage": metadata_record.get("baseImage"),
            "refreshRecommended": should_refresh,
            "reasons": reasons,
            "workloads": image_record.get("workloads"),
            "clusters": image_record.get("clusters"),
            "sightingCount": image_record.get("sightingCount"),
        }
        if family:
            evaluation["familyConfig"] = {
                "upstream": family.get("upstream"),
                "customization": family.get("customization"),
                "publication": family.get("publication"),
                "policy": family.get("policy"),
            }
        evaluations.append(_deep_clean(evaluation))
    return evaluations


def aggregate_refresh_plans(evaluations: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    families_by_name = {family.get("name"): family for family in catalog.get("families") or []}
    grouped: dict[str, dict[str, Any]] = {}
    for evaluation in evaluations:
        if not evaluation.get("refreshRecommended"):
            continue
        family_name = evaluation.get("baseFamily")
        if not family_name:
            continue
        family = families_by_name.get(family_name, {})
        if family_name not in grouped:
            grouped[family_name] = {
                "family": family_name,
                "upstream": family.get("upstream"),
                "customization": family.get("customization"),
                "publication": family.get("publication"),
                "policy": family.get("policy"),
                "impactedImages": [],
                "impactedClusters": [],
                "impactedWorkloads": [],
                "totalSightings": 0,
                "maxObservedCritical": 0,
                "maxObservedHigh": 0,
                "reasons": [],
                "evidence": [],
            }

        plan = grouped[family_name]
        plan["impactedImages"].append(evaluation.get("image"))
        plan["impactedClusters"].extend(_ensure_list(evaluation.get("clusters")))
        plan["impactedWorkloads"].extend(_ensure_list(evaluation.get("workloads")))
        plan["totalSightings"] += _int(evaluation.get("sightingCount"))
        sev = evaluation.get("severity") or {}
        plan["maxObservedCritical"] = max(plan["maxObservedCritical"], _int(sev.get("critical")))
        plan["maxObservedHigh"] = max(plan["maxObservedHigh"], _int(sev.get("high")))
        plan["reasons"].extend(_ensure_list(evaluation.get("reasons")))
        plan["evidence"].append(
            _deep_clean(
                {
                    "image": evaluation.get("image"),
                    "summaryPath": (evaluation.get("scanMetadataReference") or {}).get("summaryPath"),
                    "reportPath": (evaluation.get("scanMetadataReference") or {}).get("reportPath"),
                    "rawReportPath": (evaluation.get("scanMetadataReference") or {}).get("rawReportPath"),
                    "scanTimestamp": (evaluation.get("scanMetadataReference") or {}).get("scanTimestamp"),
                    "baseImage": evaluation.get("baseImage"),
                    "targetClasses": evaluation.get("targetClasses"),
                    "severity": evaluation.get("severity"),
                }
            )
        )

    plans = []
    for family_name, plan in grouped.items():
        plan["impactedImages"] = sorted({x for x in plan["impactedImages"] if x})
        plan["impactedClusters"] = sorted({x for x in plan["impactedClusters"] if x})
        unique_workloads = []
        seen = set()
        for workload in plan["impactedWorkloads"]:
            key = json.dumps(workload, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            unique_workloads.append(workload)
        plan["impactedWorkloads"] = unique_workloads
        plan["reasons"] = sorted({x for x in plan["reasons"] if x})
        plans.append(_deep_clean(plan))
    plans.sort(key=lambda item: item["family"])
    return plans


def summarize(evaluations: list[dict[str, Any]], plans: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "evaluatedImageCount": len(evaluations),
        "matchedScanMetadataCount": sum(1 for item in evaluations if item.get("matchedScanMetadata")),
        "refreshRecommendedImageCount": sum(1 for item in evaluations if item.get("refreshRecommended")),
        "refreshFamilyCount": len(plans),
        "families": [plan.get("family") for plan in plans],
    }


def build_acquisition_fanout(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the minimal payload needed by the upstream acquisition child.

    Full plans can include workload/evidence metadata that is useful for audit but unnecessary
    for grabbing the approved upstream base image. Keeping the fan-out payload small limits
    Argo parameter size and avoids passing extra workload context to the acquisition step.
    """
    return [
        _deep_clean(
            {
                "family": plan.get("family"),
                "upstream": plan.get("upstream"),
            }
        )
        for plan in plans
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("unique_images", help="Path to unique-images.json from dedupe phase")
    parser.add_argument("scan_metadata", help="Path to compact scan metadata JSON from existing scanner")
    parser.add_argument("family_catalog", help="Path to base-family-catalog JSON")
    parser.add_argument("output_dir", help="Directory for output JSON files")
    args = parser.parse_args()

    unique_images = load_json(args.unique_images)
    scan_metadata = load_json(args.scan_metadata)
    family_catalog = load_json(args.family_catalog)

    if not isinstance(unique_images, list):
        raise SystemExit("unique_images input must be a JSON array")
    if not isinstance(scan_metadata, list):
        raise SystemExit("scan_metadata input must be a JSON array")
    if not isinstance(family_catalog, dict):
        raise SystemExit("family_catalog input must be a JSON object")

    metadata_index = build_metadata_index(scan_metadata)
    evaluations = build_evaluations(unique_images, metadata_index, family_catalog)
    plans = aggregate_refresh_plans(evaluations, family_catalog)
    acquisition_fanout = build_acquisition_fanout(plans)
    summary = summarize(evaluations, plans)

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "image-evaluations.json").write_text(json.dumps(evaluations, indent=2))
    (outdir / "family-refresh-plans.json").write_text(json.dumps(plans, indent=2))
    (outdir / "family-refresh-plans.min.json").write_text(json.dumps(plans, separators=(",", ":")))
    (outdir / "family-acquisition-fanout.min.json").write_text(json.dumps(acquisition_fanout, separators=(",", ":")))
    (outdir / "family-refresh-summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
