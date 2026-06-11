#!/usr/bin/env python3
"""Acquire the approved upstream base image for one managed base family.

This is deliberately only the "grabbing" step. It validates that the requested
upstream comes from a corporate-approved source and, in execute mode, copies that
base image into a local OCI handoff directory for the existing cert/hardening
process to consume.

No cert injection, hardening, rebuilding, scanning, tagging, or publishing happens
in this worker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ALLOWED_SOURCE_TYPES = {"redhat-catalog", "internal-approved-registry"}
DEFAULT_ALLOWED_REGISTRIES = {"registry.redhat.io"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,126}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


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


def parse_csv_set(value: str | None, defaults: set[str]) -> set[str]:
    if not value:
        return set(defaults)
    return {item.strip() for item in value.split(",") if item.strip()}


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_deep_clean(payload), indent=2) + "\n")


def registry_from_image(image: str) -> str:
    return image.split("/", 1)[0].lower()


def is_digest_pinned(image: str, digest: str | None) -> bool:
    if digest and SHA256_RE.match(digest):
        return True
    return "@sha256:" in image


def upstream_ref(image: str, digest: str | None) -> str:
    if digest and "@sha256:" not in image:
        return f"{image}@{digest}"
    return image


def command_exists(command: str) -> bool:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    return any((Path(base) / command).exists() for base in paths if base)


def run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    result = {
        "command": command,
        "executed": True,
        "returnCode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(command)}")
    return result


def validate_plan(
    plan: dict[str, Any],
    *,
    allowed_source_types: set[str],
    allowed_registries: set[str],
    allow_unpinned_upstream: bool,
) -> list[str]:
    errors: list[str] = []
    family = _clean(plan.get("family"))
    upstream = plan.get("upstream") or {}

    if not family or not NAME_RE.match(family):
        errors.append("family must be a lowercase DNS-safe name")

    source_type = _clean(upstream.get("sourceType"))
    if source_type not in allowed_source_types:
        errors.append(f"upstream.sourceType must be one of {sorted(allowed_source_types)}")

    image = _clean(upstream.get("image"))
    if not image:
        errors.append("upstream.image is required")
    elif registry_from_image(image) not in allowed_registries:
        errors.append(f"upstream registry is not allowlisted: {registry_from_image(image)}")

    digest = _clean(upstream.get("digest"))
    if image and not is_digest_pinned(image, digest) and not allow_unpinned_upstream:
        errors.append("upstream must be pinned with sha256 digest or explicitly allowed by policy")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("family_plan", help="Path to one family refresh plan JSON object")
    parser.add_argument("output", help="Path for upstream acquisition output JSON")
    parser.add_argument("--handoff-dir", default=os.environ.get("UPSTREAM_HANDOFF_DIR", "/work/shared/upstream-bases"))
    parser.add_argument("--mode", choices=["plan", "dry-run", "execute"], default=os.environ.get("REFRESH_MODE", "dry-run"))
    parser.add_argument("--workflow-id", default=os.environ.get("ARGO_WORKFLOW_NAME", "local"))
    parser.add_argument("--allow-unpinned-approved-upstream", action="store_true")
    parser.add_argument("--allowed-source-types", default=os.environ.get("ALLOWED_UPSTREAM_SOURCE_TYPES"))
    parser.add_argument("--allowed-upstream-registries", default=os.environ.get("ALLOWED_UPSTREAM_REGISTRIES"))
    args = parser.parse_args()

    plan = load_json(args.family_plan)
    if not isinstance(plan, dict):
        raise SystemExit("family_plan must be a JSON object")

    allowed_source_types = parse_csv_set(args.allowed_source_types, DEFAULT_ALLOWED_SOURCE_TYPES)
    allowed_registries = parse_csv_set(args.allowed_upstream_registries, DEFAULT_ALLOWED_REGISTRIES)
    errors = validate_plan(
        plan,
        allowed_source_types=allowed_source_types,
        allowed_registries=allowed_registries,
        allow_unpinned_upstream=args.allow_unpinned_approved_upstream,
    )

    family = _clean(plan.get("family")) or "unknown"
    upstream = plan.get("upstream") or {}
    image = _clean(upstream.get("image")) or ""
    digest = _clean(upstream.get("digest"))
    source_ref = upstream_ref(image, digest)
    workflow_id = re.sub(r"[^a-zA-Z0-9_.-]", "-", args.workflow_id)[-32:] or "local"
    acquired_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    handoff_path = Path(args.handoff_dir) / family / f"{acquired_at}-{workflow_id}"

    commands = [
        ["skopeo", "inspect", f"docker://{source_ref}"],
        ["skopeo", "copy", f"docker://{source_ref}", f"oci:{handoff_path}:upstream"],
    ]

    command_results: list[dict[str, Any]] = []
    notes: list[str] = []
    status = "planned"
    if errors:
        status = "blocked"
        notes.extend(errors)
    elif args.mode == "execute" and not command_exists("skopeo"):
        status = "blocked"
        notes.append("missing required worker tool: skopeo")
    elif args.mode in {"plan", "dry-run"}:
        status = args.mode
        notes.append("no upstream image copy performed")
    else:
        handoff_path.mkdir(parents=True, exist_ok=True)
        for command in commands:
            command_results.append(run_command(command))
        status = "acquired"

    output = {
        "status": status,
        "family": family,
        "upstreamImage": image,
        "upstreamDigest": digest,
        "sourceReference": source_ref,
        "handoffPath": str(handoff_path),
        "nextStep": "existing cert injection and hardening process",
        "corporateSafety": {
            "mode": args.mode,
            "allowedSourceTypes": sorted(allowed_source_types),
            "allowedUpstreamRegistries": sorted(allowed_registries),
            "upstreamDigestRequired": not args.allow_unpinned_approved_upstream,
            "registryMutationAllowed": False,
        },
        "commands": command_results if args.mode == "execute" else commands,
        "notes": notes,
    }
    write_json(Path(args.output), output)


if __name__ == "__main__":
    main()
