#!/usr/bin/env python3
"""Deduplicate collected image records while preserving all impact metadata.

Purpose in the system:
- This is the boundary between inventory collection and artifact-centric processing.
- It turns many raw image sightings into one unique artifact record plus a preserved sighting map.

Why this is needed:
- The same digest may appear in many workloads, clusters, or registries.
- Scanning/remediating every sighting independently would waste time and compute.
- We still cannot lose where the image was seen, who owns it, or where PRs should land.

How it plugs in:
- Upstream collection can write either:
  - a JSON array of collected image records, or
  - the current nested `images.json` shape from the cluster image dump agent:
    `{ "epm_code": "...", "namespaces": [{"namespace": "...", "images": ["img1", "img2"]}] }`
- This script normalizes refs, expands the nested runtime inventory when needed, computes canonical keys, groups duplicates, and emits:
  - unique-images.json / .min.json
  - sightings.json
  - dedupe-summary.json
- The orchestrator then fans out scanning from unique-images, while sightings.json remains
  the evidence map that ties each artifact back to real owners and workloads.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY = "docker.io"
DEFAULT_LIBRARY_NAMESPACE = "library"
DIGEST_RE = re.compile(r"@(?P<digest>sha256:[0-9a-fA-F]{64})$")
TAG_RE = re.compile(r"^(?P<name>.+):(?P<tag>[^/:@]+)$")


def _clean(value: Any) -> Any:
    """Trim strings and collapse empty values to None."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _deep_clean(value: Any) -> Any:
    """Recursively remove empty fields so outputs stay readable and compact."""
    if isinstance(value, dict):
        cleaned = {}
        for k, v in value.items():
            v2 = _deep_clean(v)
            if v2 in (None, "", [], {}):
                continue
            cleaned[k] = v2
        return cleaned
    if isinstance(value, list):
        cleaned = [_deep_clean(v) for v in value]
        return [v for v in cleaned if v not in (None, "", [], {})]
    return _clean(value)


def _unique_non_empty(values: list[Any]) -> list[Any]:
    """Deduplicate scalar or structured values while preserving stable order."""
    seen = set()
    out = []
    for value in values:
        value = _deep_clean(value)
        if value in (None, "", [], {}):
            continue
        key = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def expand_runtime_inventory_input(payload: Any) -> list[dict[str, Any]]:
    """Accept either fully-expanded records or the current nested images.json runtime format.

    Supported formats:
    1. JSON array of already-expanded records
    2. Current cluster image dump shape:
       {
         "epm_code": "gpedev",
         "project_name": "optional",
         "clusterName": "optional",
         "namespaces": [
           {"namespace": "argo-hk", "images": ["img1", "img2"]}
         ]
       }

    The nested format does not carry rich ownership/build metadata. We expand what is available
    so the rest of the dedupe pipeline can still operate on a consistent record shape.
    """
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise SystemExit("Input must be either a JSON array of records or an images.json object")

    namespaces = payload.get("namespaces")
    if not isinstance(namespaces, list):
        raise SystemExit("Object input must contain a 'namespaces' array")

    epm_code = _clean(payload.get("epm_code"))
    project_name = _clean(payload.get("project_name"))
    cluster_name = _clean(payload.get("clusterName")) or _clean(payload.get("cluster_name"))
    environment_type = _clean(payload.get("environmentType")) or "unknown"
    source_name = project_name or epm_code or cluster_name or "cluster-image-dump"

    expanded: list[dict[str, Any]] = []
    for namespace_record in namespaces:
        if not isinstance(namespace_record, dict):
            continue
        namespace = _clean(namespace_record.get("namespace"))
        images = namespace_record.get("images") or []
        for image in images:
            image_ref = _clean(image)
            if not image_ref:
                continue
            expanded.append(
                _deep_clean(
                    {
                        "image": image_ref,
                        "sourceType": "cluster",
                        "sourceName": source_name,
                        "environmentType": environment_type,
                        "clusterName": cluster_name,
                        "namespace": namespace,
                        "ownerTeam": epm_code,
                        "notes": "Expanded from nested images.json runtime inventory",
                        "metadata": {
                            "epmCode": epm_code,
                            "projectName": project_name,
                        },
                    }
                )
            )

    return expanded


def normalize_image_reference(image: str | None) -> dict[str, Any]:
    """Parse and normalize an image ref into registry/repository/tag/digest parts.

    Why this exists:
    - Inputs may come from clusters, registries, or local submissions with inconsistent formatting.
    - The system needs a normalized identity before dedupe can be trusted.
    """
    if not image:
        return {
            "original": None,
            "normalizedName": None,
            "normalizedReference": None,
            "tag": None,
            "digest": None,
            "registry": None,
            "repository": None,
        }

    raw_image = image.strip()
    image = raw_image
    digest = None
    digest_match = DIGEST_RE.search(image)
    if digest_match:
        digest = digest_match.group("digest").lower()
        image = image[: digest_match.start()]

    tag = None
    tag_match = TAG_RE.match(image)
    if tag_match:
        image = tag_match.group("name")
        tag = tag_match.group("tag")

    parts = image.split("/")
    first = parts[0] if parts else ""
    if "." in first or ":" in first or first == "localhost":
        registry = first.lower()
        path_parts = parts[1:]
    else:
        registry = DEFAULT_REGISTRY
        path_parts = parts

    if len(path_parts) == 1 and path_parts[0]:
        path_parts = [DEFAULT_LIBRARY_NAMESPACE, path_parts[0]]

    repository = "/".join(path_parts).lower() if path_parts else None
    normalized_name = f"{registry}/{repository}" if repository else registry
    normalized_reference = normalized_name
    if digest:
        normalized_reference = f"{normalized_name}@{digest}"
    elif tag:
        normalized_reference = f"{normalized_name}:{tag}"

    return {
        "original": raw_image,
        "normalizedName": normalized_name,
        "normalizedReference": normalized_reference,
        "tag": tag,
        "digest": digest,
        "registry": registry,
        "repository": repository,
    }


def canonical_key(record: dict[str, Any], normalized: dict[str, Any]) -> str:
    """Compute the grouping key for an image record.

    Key policy:
    1. Prefer immutable digest identity whenever possible.
    2. If digest is missing, fall back to a Dockerfile/source-derived temporary identity.

    Why the fallback exists:
    - Teams often know repo + Dockerfile + tag before they know the final digest.
    - We still need to group those records without pretending the tag alone is immutable.
    """
    explicit_digest = _clean(record.get("digest"))
    digest = explicit_digest.lower() if isinstance(explicit_digest, str) else normalized.get("digest")
    if digest and normalized.get("normalizedName"):
        return f"{normalized['normalizedName']}@{digest}"

    dockerfile_identity = [
        _clean(record.get("sourceRepoUrl")),
        _clean(record.get("sourceRepoPath")),
        _clean(record.get("dockerfilePath")),
        normalized.get("normalizedName"),
        _clean(record.get("tag")) or normalized.get("tag") or "latest",
    ]
    return "dockerfile-source::" + "::".join(str(x or "UNKNOWN") for x in dockerfile_identity)


def build_sighting(record: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    """Extract the per-sighting metadata we must never lose.

    Why this exists:
    - The unique artifact record is for scan/remediation efficiency.
    - The sighting record is for blast-radius reporting, ownership lookup, and PR routing.
    """
    return _deep_clean(
        {
            "sourceType": record.get("sourceType"),
            "sourceName": record.get("sourceName"),
            "environmentType": record.get("environmentType"),
            "clusterName": record.get("clusterName"),
            "registryName": record.get("registryName"),
            "machineName": record.get("machineName"),
            "namespace": record.get("namespace"),
            "workloadKind": record.get("workloadKind"),
            "workloadName": record.get("workloadName"),
            "ownerTeam": record.get("ownerTeam"),
            "ownerContact": record.get("ownerContact"),
            "sourceRepoUrl": record.get("sourceRepoUrl"),
            "sourceRepoPath": record.get("sourceRepoPath"),
            "dockerfilePath": record.get("dockerfilePath"),
            "helmChartPath": record.get("helmChartPath"),
            "buildPipelineUrl": record.get("buildPipelineUrl"),
            "prTargetRepoUrl": record.get("prTargetRepoUrl") or record.get("sourceRepoUrl"),
            "prTargetBranch": record.get("prTargetBranch"),
            "imageReferenceSeen": record.get("image") or record.get("imageReference"),
            "normalizedImageName": normalized.get("normalizedName"),
            "normalizedReference": normalized.get("normalizedReference"),
            "digest": _clean(record.get("digest")) or normalized.get("digest"),
            "labels": record.get("labels"),
            "annotations": record.get("annotations"),
            "submittedAt": record.get("submittedAt"),
            "notes": record.get("notes"),
        }
    )


def aggregate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Group raw inventory records into unique artifacts plus a full sighting map.

    This is the heart of the artifact-centric model:
    - one grouped artifact record = one thing to scan/remediate
    - many sightings = many impacted places/teams to report back to
    """
    grouped: dict[str, dict[str, Any]] = {}
    sightings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    summary = {
        "inputRecordCount": len(records),
        "uniqueImageCount": 0,
        "deduplicatedRecordCount": 0,
        "uniqueWithDigestCount": 0,
        "uniqueWithoutDigestCount": 0,
        "sourceTypeCounts": {},
    }
    source_counts: defaultdict[str, int] = defaultdict(int)

    for record in records:
        normalized = normalize_image_reference(_clean(record.get("image") or record.get("imageReference")))
        key = canonical_key(record, normalized)
        sighting = build_sighting(record, normalized)
        source_counts[sighting.get("sourceType", "unknown")] += 1
        sightings[key].append(sighting)

        if key not in grouped:
            # Seed the unique artifact record from the first observation, then enrich it as more
            # sightings arrive.
            grouped[key] = {
                "canonicalKey": key,
                "image": normalized.get("normalizedReference") or normalized.get("normalizedName"),
                "normalizedImageName": normalized.get("normalizedName"),
                "registry": normalized.get("registry"),
                "repository": normalized.get("repository"),
                "tag": _clean(record.get("tag")) or normalized.get("tag"),
                "digest": _clean(record.get("digest")) or normalized.get("digest"),
                "sourceRepoUrl": _clean(record.get("sourceRepoUrl")),
                "sourceRepoPath": _clean(record.get("sourceRepoPath")),
                "dockerfilePath": _clean(record.get("dockerfilePath")),
                "helmChartPath": _clean(record.get("helmChartPath")),
                "prTargetRepoUrl": _clean(record.get("prTargetRepoUrl")) or _clean(record.get("sourceRepoUrl")),
                "prTargetBranch": _clean(record.get("prTargetBranch")),
                "buildPipelineUrl": _clean(record.get("buildPipelineUrl")),
                "ownerTeams": [],
                "ownerContacts": [],
                "environments": [],
                "sourceTypes": [],
                "sourceNames": [],
                "clusters": [],
                "workloads": [],
                "sightingCount": 0,
            }

        agg = grouped[key]
        agg["ownerTeams"].append(_clean(record.get("ownerTeam")))
        agg["ownerContacts"].append(record.get("ownerContact"))
        agg["environments"].append(_clean(record.get("environmentType")))
        agg["sourceTypes"].append(_clean(record.get("sourceType")))
        agg["sourceNames"].append(_clean(record.get("sourceName")))
        agg["clusters"].append(_clean(record.get("clusterName")))
        agg["workloads"].append(
            _deep_clean(
                {
                    "clusterName": record.get("clusterName"),
                    "namespace": record.get("namespace"),
                    "workloadKind": record.get("workloadKind"),
                    "workloadName": record.get("workloadName"),
                }
            )
        )

        # Preserve the first non-empty routing/ownership/build fields we learn for the artifact.
        if not agg.get("sourceRepoUrl") and _clean(record.get("sourceRepoUrl")):
            agg["sourceRepoUrl"] = _clean(record.get("sourceRepoUrl"))
        if not agg.get("sourceRepoPath") and _clean(record.get("sourceRepoPath")):
            agg["sourceRepoPath"] = _clean(record.get("sourceRepoPath"))
        if not agg.get("dockerfilePath") and _clean(record.get("dockerfilePath")):
            agg["dockerfilePath"] = _clean(record.get("dockerfilePath"))
        if not agg.get("helmChartPath") and _clean(record.get("helmChartPath")):
            agg["helmChartPath"] = _clean(record.get("helmChartPath"))
        if not agg.get("prTargetRepoUrl") and _clean(record.get("prTargetRepoUrl")):
            agg["prTargetRepoUrl"] = _clean(record.get("prTargetRepoUrl"))
        if not agg.get("prTargetBranch") and _clean(record.get("prTargetBranch")):
            agg["prTargetBranch"] = _clean(record.get("prTargetBranch"))
        if not agg.get("buildPipelineUrl") and _clean(record.get("buildPipelineUrl")):
            agg["buildPipelineUrl"] = _clean(record.get("buildPipelineUrl"))
        if not agg.get("digest") and (_clean(record.get("digest")) or normalized.get("digest")):
            agg["digest"] = _clean(record.get("digest")) or normalized.get("digest")
        if not agg.get("image") and (normalized.get("normalizedReference") or normalized.get("normalizedName")):
            agg["image"] = normalized.get("normalizedReference") or normalized.get("normalizedName")

    unique_images: list[dict[str, Any]] = []
    for key, agg in grouped.items():
        current_sightings = _unique_non_empty(sightings[key])
        agg["ownerTeams"] = _unique_non_empty(agg["ownerTeams"])
        agg["ownerContacts"] = _unique_non_empty(agg["ownerContacts"])
        agg["environments"] = _unique_non_empty(agg["environments"])
        agg["sourceTypes"] = _unique_non_empty(agg["sourceTypes"])
        agg["sourceNames"] = _unique_non_empty(agg["sourceNames"])
        agg["clusters"] = _unique_non_empty(agg["clusters"])
        agg["workloads"] = _unique_non_empty(agg["workloads"])
        agg["sightingCount"] = len(current_sightings)
        unique_images.append(_deep_clean(agg))
        sightings[key] = current_sightings

    unique_images.sort(key=lambda item: item["canonicalKey"])
    ordered_sightings = {k: sightings[k] for k in sorted(sightings)}

    summary["uniqueImageCount"] = len(unique_images)
    summary["deduplicatedRecordCount"] = len(records) - len(unique_images)
    summary["uniqueWithDigestCount"] = sum(1 for item in unique_images if item.get("digest"))
    summary["uniqueWithoutDigestCount"] = sum(1 for item in unique_images if not item.get("digest"))
    summary["sourceTypeCounts"] = dict(sorted(source_counts.items()))

    return unique_images, ordered_sightings, summary


def load_inventory_records(input_path: Path) -> list[dict[str, Any]]:
    """Load either one inventory JSON file or a directory full of per-cluster `images.json` files.

    Why this exists:
    - The real environment emits one `images.json` per cluster because there are many clusters.
    - The rest of the remediation pipeline still wants one normalized list of runtime sightings.

    How it plugs in:
    - Collection can drop many prod-shaped JSON files into one shared directory.
    - This loader expands each file using the same runtime inventory contract, then concatenates them
      before the normal artifact dedupe logic runs.
    """
    if input_path.is_dir():
        json_files = sorted(path for path in input_path.glob("*.json") if path.is_file())
        if not json_files:
            raise SystemExit(f"No JSON files found under inventory directory: {input_path}")

        expanded_records: list[dict[str, Any]] = []
        for json_file in json_files:
            payload = json.loads(json_file.read_text())
            records = expand_runtime_inventory_input(payload)
            if not isinstance(records, list):
                raise SystemExit(f"Expanded input from {json_file} must be a JSON array of records")
            expanded_records.extend(records)
        return expanded_records

    payload = json.loads(input_path.read_text())
    records = expand_runtime_inventory_input(payload)
    if not isinstance(records, list):
        raise SystemExit(f"Expanded input from {input_path} must be a JSON array of records")
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to one inventory JSON file or a directory of per-cluster JSON files")
    parser.add_argument("output_dir", help="Directory for output JSON files")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_inventory_records(input_path)

    unique_images, sightings, summary = aggregate_records(records)

    (output_dir / "unique-images.json").write_text(json.dumps(unique_images, indent=2))
    (output_dir / "unique-images.min.json").write_text(json.dumps(unique_images, separators=(",", ":")))
    (output_dir / "sightings.json").write_text(json.dumps(sightings, indent=2))
    (output_dir / "dedupe-summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
