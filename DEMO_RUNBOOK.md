# Demo Runbook

This demo shows the registry remediation flow without needing live registry access.

## What The Demo Proves

1. The platform expects an `images.json` file containing all running image references for the target cluster/environment scope.
2. It deduplicates repeated runtime image sightings.
3. It joins deduplicated images to existing Aqua/Trivy scan metadata.
4. It maps vulnerable app images to managed base families.
5. It creates one upstream acquisition plan per affected base family.
6. It dry-runs the approved upstream grab step without mutating registries.

## Prerequisites

- Python 3
- `jq` for the optional per-family dry-run loop
- Helm only if you want to render/lint the chart

No network or registry access is required for the dry-run demo.

## Run The Local Flow

From the repo root:

```bash
python3 scripts/deduplicate_image_records.py \
  examples/collected-image-records.example.json \
  /tmp/scotia-demo-dedupe

python3 scripts/plan_base_refresh_from_scan_metadata.py \
  examples/unique-images-for-refresh.example.json \
  examples/scan-metadata.example.json \
  config/base-family-catalog.example.json \
  /tmp/scotia-demo-plan

cat /tmp/scotia-demo-dedupe/dedupe-summary.json
cat /tmp/scotia-demo-plan/family-refresh-summary.json
```

Expected planner result:

```json
{
  "evaluatedImageCount": 3,
  "matchedScanMetadataCount": 3,
  "refreshRecommendedImageCount": 3,
  "refreshFamilyCount": 3,
  "families": [
    "ubi9-nginx",
    "ubi9-openjdk-17",
    "ubi9-python-311"
  ]
}
```

The dedupe summary for the expanded prod-shaped inventory should show 15 input
image entries collapsed to 11 unique image records.

## Dry-Run Upstream Acquisition

```bash
for i in 0 1 2; do
  jq ".[$i]" /tmp/scotia-demo-plan/family-acquisition-fanout.min.json > /tmp/scotia-demo-family-$i.json
  python3 scripts/refresh_base_family.py \
    /tmp/scotia-demo-family-$i.json \
    /tmp/scotia-demo-acquire-$i.json \
    --handoff-dir /tmp/scotia-demo-upstream-bases \
    --mode dry-run \
    --workflow-id demo
done

for f in /tmp/scotia-demo-acquire-*.json; do
  jq '{status,family,sourceReference,handoffPath,corporateSafety,notes}' "$f"
done
```

Expected behavior:

- status is `dry-run`
- every source reference is digest-pinned
- no registry mutation occurs
- handoff paths are generated for downstream cert/hardening processing

## Helm Validation

If Helm is available:

```bash
helm lint helm/cluster-scan \
  --set namespace=registry-remediation \
  --set serviceAccount.name=registry-remediator \
  --set argo.pvc.claimName=registry-remediator-shared-work \
  --set images.builder.repository=registry.corp/platform/skopeo-worker \
  --set images.builder.tag=approved

helm template smoke helm/cluster-scan \
  --show-only templates/workflowtemplate-remediate-image.yaml \
  --set namespace=registry-remediation \
  --set serviceAccount.name=registry-remediator \
  --set argo.pvc.claimName=registry-remediator-shared-work \
  --set images.builder.repository=registry.corp/platform/skopeo-worker \
  --set images.builder.tag=approved
```

## Production Gaps To Say Out Loud

- Replace placeholder digests with corporate-approved pinned digests.
- Provide the real complete `images.json`.
- Provide real scanner metadata.
- Use an approved worker image with `python3` and `skopeo`.
- Wire Red Hat or internal registry credentials.
- Connect the upstream handoff directory to the existing cert/hardening/rebuild process.
- Add state tracking to avoid repeated refresh storms.
