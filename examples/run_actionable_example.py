#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from filter_trivy_actionable import flatten_findings, summarize

report = json.loads(Path('/home/ziyad/projects/scotiabank-registry-remediation/examples/trivy-report.example.json').read_text())
findings = flatten_findings(report, {'CRITICAL', 'HIGH'})
summary = summarize(findings)
outdir = Path('/home/ziyad/projects/scotiabank-registry-remediation/examples/actionable-output')
outdir.mkdir(parents=True, exist_ok=True)
(outdir / 'actionable-findings.json').write_text(json.dumps(findings, indent=2))
(outdir / 'actionable-summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
