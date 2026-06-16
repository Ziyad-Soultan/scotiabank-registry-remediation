#!/usr/bin/env python3
"""Scan deduplicated runtime artifacts with Trivy and emit compact scan metadata.

Purpose in the system:
- This is the new upstream bridge between dedupe and family refresh planning.
- It scans each unique runtime artifact once, not once per workload sighting.
- It preserves the compact `scan-metadata/v1` contract the downstream planner already expects.

Why this is needed:
- The repo used to assume some other production scanner pipeline already emitted scan metadata.
- The real environment now gives us end-to-end ownership, so this repo needs its own scan stage.
- Keeping the scan output in the same compact JSON contract avoids unnecessary downstream refactoring.

How it plugs in:
- Input A: `unique-images.json` from the dedupe step.
- Input B: the base-family catalog, used only for lineage hints (`baseFamily`, `managedBaseImage`).
- Output: one aggregated `scan-metadata.json` file consumed by `plan_base_refresh_from_scan_metadata.py`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .trivy_to_scan_metadata import count_findings
except ImportError:  # pragma: no cover - direct script execution
    from trivy_to_scan_metadata import count_findings


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


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


def write_json(path: str, payload: Any) -> None:
    Path(path).write_text(json.dumps(_deep_clean(payload), indent=2) + "\n")


def match_family(image_record: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any] | None:
    image_name = _clean(image_record.get("normalizedImageName") or image_record.get("image")) or ""
    for family in catalog.get("families") or []:
        selectors = family.get("selectors") or {}
        for prefix in selectors.get("repositoryPrefixes") or []:
            if image_name.startswith(prefix):
                return family
        for regex in selectors.get("imageRegexes") or []:
            if re.search(regex, image_name):
                return family
    return None


def run_trivy(image: str, raw_report_path: Path, timeout_seconds: int) -> dict[str, Any]:
    command = [
        "trivy",
        "image",
        "--severity",
        "HIGH,CRITICAL",
        "--format",
        "json",
        "--output",
        str(raw_report_path),
        image,
    ]
    completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Trivy scan failed for {image}: rc={completed.returncode} stderr={completed.stderr[-800:]}"
        )
    return json.loads(raw_report_path.read_text())


def placeholder_record(image_record: dict[str, Any], family: dict[str, Any] | None, raw_report_path: Path) -> dict[str, Any]:
    return _deep_clean(
        {
            "schemaVersion": "scan-metadata/v1",
            "image": image_record.get("image"),
            "digest": image_record.get("digest"),
            "normalizedReference": image_record.get("image"),
            "normalizedImageName": image_record.get("normalizedImageName"),
            "canonicalKey": image_record.get("canonicalKey"),
            "scanner": "trivy",
            "scannerVersion": "placeholder",
            "scanTimestamp": utc_now(),
            "baseFamily": family.get("name") if family else None,
            "managedBaseImage": bool(family),
            "targetClasses": [],
            "criticalCount": 0,
            "highCount": 0,
            "fixableCriticalCount": 0,
            "fixableHighCount": 0,
            "rawReportPath": str(raw_report_path),
            "notes": [
                "placeholder-scan-record",
                "replace this script or enable execute mode with a worker image that has Trivy",
            ],
        }
    )


def build_metadata_record(
    image_record: dict[str, Any],
    family: dict[str, Any] | None,
    report: dict[str, Any],
    raw_report_path: Path,
) -> dict[str, Any]:
    counts = count_findings(report)
    return _deep_clean(
        {
            "schemaVersion": "scan-metadata/v1",
            "image": _clean(image_record.get("image")) or _clean(report.get("ArtifactName")),
            "digest": _clean(image_record.get("digest")),
            "normalizedReference": _clean(image_record.get("image")),
            "normalizedImageName": _clean(image_record.get("normalizedImageName")),
            "canonicalKey": _clean(image_record.get("canonicalKey")),
            "scanner": "trivy",
            "scanTimestamp": _clean(report.get("CreatedAt")) or utc_now(),
            "baseFamily": family.get("name") if family else None,
            "baseImage": {
                "family": family.get("name") if family else None,
                "source": "catalog-selector-match" if family else "unmatched",
            },
            "managedBaseImage": bool(family),
            "targetClasses": counts["targetClasses"],
            "criticalCount": counts["criticalCount"],
            "highCount": counts["highCount"],
            "fixableCriticalCount": counts["fixableCriticalCount"],
            "fixableHighCount": counts["fixableHighCount"],
            "rawReportPath": str(raw_report_path),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("unique_images", help="Path to unique-images.json")
    parser.add_argument("family_catalog", help="Path to base-family catalog JSON")
    parser.add_argument("output", help="Path to aggregated scan metadata JSON")
    parser.add_argument("--raw-report-dir", default="/tmp/trivy-raw")
    parser.add_argument("--mode", choices=["plan", "dry-run", "execute"], default="dry-run")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    unique_images = load_json(args.unique_images)
    catalog = load_json(args.family_catalog)
    if not isinstance(unique_images, list):
        raise SystemExit("unique_images must be a JSON array")

    raw_report_dir = Path(args.raw_report_dir)
    raw_report_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for index, image_record in enumerate(unique_images):
        image = _clean(image_record.get("image"))
        if not image:
            continue
        family = match_family(image_record, catalog)
        raw_report_path = raw_report_dir / f"scan-{index:05d}.json"

        if args.mode in {"plan", "dry-run"}:
            records.append(placeholder_record(image_record, family, raw_report_path))
            continue

        report = run_trivy(image, raw_report_path, args.timeout_seconds)
        records.append(build_metadata_record(image_record, family, report, raw_report_path))

    write_json(args.output, records)


if __name__ == "__main__":
    main()
