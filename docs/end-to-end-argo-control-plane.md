# End-to-End Argo Control Plane

## Purpose
Document the updated upstream architecture now that this repo owns the scanner and remediation control plane end to end.

## What changed
Old assumption:
- some other production chart already collected inventory and produced scan metadata
- this repo only consumed that metadata downstream

New reality:
- the production chart never shipped
- this repo now needs to own the control plane from upstream inventory handoff through family refresh handoff
- the rebuild/cert logic can remain external for now, but the control-plane contract should exist here

## Design goal
Keep the existing repo shape and planner logic as intact as possible.

That means:
- keep the nested per-cluster `images.json` contract exactly as already matched to work expectations
- dedupe immediately after collection handoff
- scan only the deduplicated unique image set
- keep the compact `scan-metadata/v1` contract so the existing planner still works
- keep family-level refresh planning
- keep the current `refresh_base_family.py` upstream acquisition step
- add only a placeholder rebuild handoff so the real build/cert repo can be copied in later with minimal churn

## Runtime inventory contract
The upstream collector should drop one prod-shaped JSON file per cluster into a shared directory.

Expected directory:
- `/work/shared/cluster-images`

Expected file pattern:
- `*.json`

Expected file contents per cluster:

```json
{
  "epm_code": "gpedev",
  "project_name": "argo-workflows",
  "clusterName": "rancher-prod-a",
  "environmentType": "cloud",
  "namespaces": [
    {
      "namespace": "argo-hk",
      "images": [
        "af.cds.bns:5002/aqua/scanner:2022.4.484",
        "quay.io/argoproj/argocli:v3.6.7"
      ]
    }
  ]
}
```

Important:
- do not change this JSON shape
- do not pre-merge it into some new schema unless you absolutely have to
- the dedupe script in this repo now accepts a directory of these files directly

## End-to-end workflow

### 1. Cluster inventory collection happens upstream
This repo assumes some collector chart/job already writes one `images.json` per cluster into the shared inventory directory.

Why keep it this way:
- you already matched this contract to what work expects
- there are many clusters
- least refactor wins here

### 2. inventory-dedup child
Input:
- directory of per-cluster `images.json` files

Action:
- expand each file into normalized runtime records
- merge them together
- dedupe repeated images across clusters/namespaces/workloads

Outputs:
- `unique-images.json`
- `unique-images.min.json`
- `sightings.json`
- `dedupe-summary.json`

### 3. scan-unique-images child
Input:
- `unique-images.json`
- base-family catalog

Action:
- scan each unique runtime artifact once with Trivy
- write raw reports to `/work/shared/trivy-raw`
- convert the results into one aggregated compact `scan-metadata.json`

Output contract:
- `scan-metadata/v1`

Reason for this design:
- it preserves the current planner interface
- it avoids rewriting the planner around raw Trivy blobs
- it avoids scanning the same image once per workload sighting

### 4. plan-refresh-from-scan-metadata child
Input:
- `unique-images.json`
- `scan-metadata.json`
- base-family catalog

Action:
- match runtime images to metadata
- identify fixable High/Critical base/runtime issues
- map impacted runtime images to managed internal base families
- emit one refresh plan per family

Outputs:
- `image-evaluations.json`
- `family-refresh-plans.json`
- `family-acquisition-fanout.min.json`
- `family-refresh-summary.json`

### 5. refresh-base-family child fan-out
Input:
- one family plan at a time

Step A: acquire upstream base
- use `refresh_base_family.py`
- validate allowed source types and registries
- default to dry-run
- copy approved upstream base into a shared handoff dir when execute mode is enabled

Step B: placeholder rebuild handoff
- use `rebuild_family_candidate.py`
- no fake cert injection or fake publish logic here
- just emit the stable JSON contract the real rebuild repo should satisfy later

This keeps the architecture honest while minimizing refactoring.

## Upstream source strategy
Current reality:
- there is no curated internal safe-upstream list yet
- the team currently grabs newer bases manually from Red Hat

Recommended interim policy:
- treat `registry.redhat.io` as the authoritative upstream registry
- keep upstream source types constrained to Red Hat catalog or internal-approved-registry
- keep execute mode wanting digest-pinned references
- let family catalog entries hold the chosen stream/family names
- later add a real approval/state layer once the end-to-end flow is working

In plain English:
- yes, use Red Hat as upstream for now
- no, don’t pretend “latest tag from vendor” is magically safe just because it is convenient

## Why Argo still makes sense
The updated architecture is still a strong Argo fit because the work is:
- Kubernetes-native
- containerized
- artifact/PVC-driven
- parallel at the image/family level
- closer to ops automation than ETL analytics

This repo should use:
- Helm for packaging/config
- Argo Workflows for execution
- ArgoCD if you want GitOps delivery

Airflow can still exist later for:
- reports
- trend summaries
- governance dashboards
- notifications

But it should not be the main execution engine for the scan/rebuild/publish path unless politics force that decision.

## Files that now represent the upstream architecture
- `scripts/deduplicate_image_records.py`
- `scripts/scan_unique_images.py`
- `scripts/plan_base_refresh_from_scan_metadata.py`
- `scripts/refresh_base_family.py`
- `scripts/rebuild_family_candidate.py`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-inventory-dedup.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-scan-unique-images.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-scan-metadata-planner.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-remediate-image.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-orchestrator.yaml`

## Known intentional gaps
Still placeholder by design:
- real collector integration from your work charts into the shared inventory directory
- real production scanner worker image with Python + Trivy
- family-catalog approval process and pinned production digests
- copied-in cert injection / hardening / rebuild logic from the work repo
- candidate rescan + publish gate
- cooldown/state tracking per family

That is okay.
The point of this pass is to make the upstream control plane sane without blowing up the downstream repo structure.
