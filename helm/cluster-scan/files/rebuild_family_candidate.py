#!/usr/bin/env python3
"""Placeholder downstream rebuild handoff for one managed base family.

Purpose in the system:
- Document the control-plane boundary after upstream base acquisition.
- Hold the family plan plus acquired upstream reference in one JSON handoff.
- Give the work-laptop rebuild repo a stable contract to plug into later.

Why this is needed:
- The repo now owns the end-to-end architecture, but the real rebuild/cert logic already lives elsewhere.
- We want minimal refactoring now, not a fake rebuild implementation that lies about being complete.

How it plugs in:
- Input A: original family refresh plan.
- Input B: upstream acquisition output from `refresh_base_family.py`.
- Output: placeholder rebuild handoff JSON for the future cert/hardening/build worker.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


def write_json(path: str, payload: Any) -> None:
    Path(path).write_text(json.dumps(_deep_clean(payload), indent=2) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("family_plan", help="Path to family plan JSON")
    parser.add_argument("acquisition_output", help="Path to upstream acquisition output JSON")
    parser.add_argument("output", help="Path to rebuild handoff JSON")
    parser.add_argument("--mode", choices=["placeholder", "execute"], default="placeholder")
    parser.add_argument("--work-repo-path", default="REPLACE WITH work-laptop rebuild repo path")
    parser.add_argument("--workflow-id", default="local")
    args = parser.parse_args()

    family_plan = load_json(args.family_plan)
    acquisition_output = load_json(args.acquisition_output)

    family = _clean(family_plan.get("family")) or "unknown"
    publication = family_plan.get("publication") or {}
    candidate_repo = _clean(publication.get("targetRepository")) or "REPLACE WITH target internal registry repository"

    payload = {
        "status": "placeholder" if args.mode == "placeholder" else "not-implemented",
        "timestamp": utc_now(),
        "workflowId": args.workflow_id,
        "family": family,
        "upstreamAcquisition": acquisition_output,
        "candidateBuild": {
            "workRepoPath": args.work_repo_path,
            "expectedInput": {
                "upstreamHandoffPath": acquisition_output.get("handoffPath"),
                "sourceReference": acquisition_output.get("sourceReference"),
                "familyPlan": family_plan,
            },
            "expectedOutput": {
                "candidateRepository": candidate_repo,
                "candidateTag": f"{family}-REPLACE-WITH-immutable-build-tag",
                "candidateDigest": "REPLACE WITH candidate digest after build and push",
            },
            "requiredFutureSteps": [
                "copy in the real cert injection / hardening / build logic from the work repo",
                "rebuild candidate image from the acquired upstream base",
                "rescan candidate image with Trivy",
                "gate publication on critical/high policy",
                "publish approved candidate to the internal registry",
            ],
        },
        "notes": [
            "placeholder rebuild handoff only",
            "intended to minimize refactoring until the real rebuild worker is copied from the work repo",
        ],
    }
    write_json(args.output, payload)


if __name__ == "__main__":
    main()
