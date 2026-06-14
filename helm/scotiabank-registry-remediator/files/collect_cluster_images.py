#!/usr/bin/env python3
"""Collect runtime images from Kubernetes clusters into the existing images.json shape.

Purpose in the system:
- This is the missing cluster-side bridge the repo previously admitted it did not have.
- It queries each configured prod cluster, extracts running container images, and writes one
  dedupe-safe `images.json` file per cluster.

Why this is needed:
- The rest of the pipeline already knows how to ingest a directory of per-cluster images.json files.
- Without a real collector, that contract was just vibes and wishful thinking.

How it plugs in:
- Provide a cluster config JSON file listing prod cluster names/contexts and ownership fields.
- Run this script before dedupe.
- Dedupe can then consume the output directory directly and preserve cross-cluster sightings.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def safe_cluster_filename(cluster_name: str) -> str:
    cleaned = SAFE_NAME_RE.sub("-", cluster_name.strip()).strip("-._")
    return cleaned or "cluster"


def iter_pod_images(pod: dict[str, Any]) -> list[str]:
    spec = pod.get("spec") or {}
    images: list[str] = []
    for field in ("containers", "initContainers", "ephemeralContainers"):
        for container in spec.get(field) or []:
            image = _clean((container or {}).get("image"))
            if image:
                images.append(image)
    return images


def build_inventory_payload(
    pod_list: dict[str, Any],
    *,
    cluster_name: str,
    epm_code: str,
    project_name: str | None = None,
    environment_type: str = "prod",
) -> dict[str, Any]:
    namespace_images: dict[str, list[str]] = defaultdict(list)
    for pod in pod_list.get("items") or []:
        namespace = _clean(((pod.get("metadata") or {}).get("namespace")))
        if not namespace:
            continue
        namespace_images[namespace].extend(iter_pod_images(pod))

    namespaces = [
        {"namespace": namespace, "images": _unique(images)}
        for namespace, images in sorted(namespace_images.items())
        if _unique(images)
    ]

    return {
        "epm_code": epm_code,
        "project_name": project_name,
        "clusterName": cluster_name,
        "environmentType": environment_type,
        "namespaces": namespaces,
    }


def run_kubectl(context: str, kubectl_bin: str, timeout_seconds: int) -> dict[str, Any]:
    command = [kubectl_bin, "--context", context, "get", "pods", "--all-namespaces", "-o", "json"]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError(f"kubectl failed for context {context}: rc={completed.returncode} stderr={completed.stderr[-800:]}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"kubectl output for context {context} was not a JSON object")
    return payload


def write_inventory_file(payload: dict[str, Any], output_dir: Path) -> Path:
    cluster_name = _clean(payload.get("clusterName")) or "cluster"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{safe_cluster_filename(cluster_name)}.images.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def load_cluster_config(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        payload = payload.get("clusters")
    if not isinstance(payload, list):
        raise SystemExit("cluster config must be a JSON array or an object with a 'clusters' array")
    return payload


def collect_clusters(config_records: list[dict[str, Any]], output_dir: Path, kubectl_bin: str, timeout_seconds: int) -> dict[str, Any]:
    written_files: list[str] = []
    cluster_summaries: list[dict[str, Any]] = []
    for record in config_records:
        cluster_name = _clean(record.get("clusterName") or record.get("name"))
        context = _clean(record.get("kubectlContext") or record.get("context")) or cluster_name
        epm_code = _clean(record.get("epm_code") or record.get("epmCode"))
        project_name = _clean(record.get("project_name") or record.get("projectName"))
        environment_type = _clean(record.get("environmentType")) or "prod"
        if not cluster_name or not epm_code:
            raise SystemExit("each cluster record must include clusterName/name and epm_code/epmCode")

        pod_list = run_kubectl(context, kubectl_bin, timeout_seconds)
        payload = build_inventory_payload(
            pod_list,
            cluster_name=cluster_name,
            epm_code=epm_code,
            project_name=project_name,
            environment_type=environment_type,
        )
        out_path = write_inventory_file(payload, output_dir)
        written_files.append(str(out_path))
        cluster_summaries.append(
            {
                "clusterName": cluster_name,
                "kubectlContext": context,
                "epm_code": epm_code,
                "project_name": project_name,
                "namespaceCount": len(payload.get("namespaces") or []),
                "imageCount": sum(len(ns.get("images") or []) for ns in payload.get("namespaces") or []),
                "outputPath": str(out_path),
            }
        )

    summary = {
        "clusterCount": len(cluster_summaries),
        "outputDirectory": str(output_dir),
        "files": written_files,
        "clusters": cluster_summaries,
    }
    (output_dir / "collection-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cluster_config", help="Path to JSON array of prod clusters to scan")
    parser.add_argument("output_dir", help="Directory where one images.json per cluster will be written")
    parser.add_argument("--kubectl-bin", default="kubectl")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    config_records = load_cluster_config(Path(args.cluster_config))
    collect_clusters(config_records, Path(args.output_dir), args.kubectl_bin, args.timeout_seconds)


if __name__ == "__main__":
    main()
