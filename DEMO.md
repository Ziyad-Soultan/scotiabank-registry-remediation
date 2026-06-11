# Demo Script

Use this for a short walkthrough demo. Everything below works offline with the
sample files in this repo.

## Opening Line

```text
This prototype does not replace the existing scanner. It consumes the scanner's
running image inventory and vulnerability metadata, deduplicates runtime images,
maps them to managed base families, and dry-runs acquisition of the approved
upstream base by digest.
```

## 1. Show The Running Image Inventory

File:

```text
examples/collected-image-records.example.json
```

Say:

```text
This is the same nested images.json shape we expect in production. The important
point is that this file is the complete running image inventory for the scope we
are remediating.
```

Command:

```bash
python3 scripts/deduplicate_image_records.py \
  examples/collected-image-records.example.json \
  /tmp/scotia-demo-dedupe

cat /tmp/scotia-demo-dedupe/dedupe-summary.json
```

Expected shape:

```json
{
  "inputRecordCount": 15,
  "uniqueImageCount": 11,
  "deduplicatedRecordCount": 4
}
```

Say:

```text
The dedupe step collapses repeated sightings, but preserves where each image was
seen. That is important because remediation planning should happen once per
artifact, while reporting still needs workload impact.
```

## 2. Show Scanner Metadata

File:

```text
examples/scan-metadata.example.json
```

Say:

```text
This is compact Aqua/Trivy metadata. We are not archiving and rescanning every
image here. We only need identity, severity counts, fixable counts, target class,
managed-base signal, and preferably baseFamily.
```

Important:

```text
This prototype does not rescan the running images from images.json. It reuses
the existing scanner metadata. A later downstream process can rescan rebuilt
candidate base images before publication, but that is outside this demo worker.
```

If the existing child scanner only has raw Trivy JSON, it can adapt it into this
standard contract with:

```bash
python3 scripts/trivy_to_scan_metadata.py \
  examples/trivy-report.example.json \
  /tmp/scotia-demo-trivy-metadata.json \
  --image internal-registry.example.com/platform/python-api:1.2.3 \
  --digest sha256:1111111111111111111111111111111111111111111111111111111111111111 \
  --base-family ubi9-python-311 \
  --base-image registry.corp/base/ubi9-python-311:approved \
  --base-digest sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
  --scanner-version 0.52.2 \
  --managed-base-image \
  --raw-report-path examples/trivy-report.example.json
```

## 3. Show The Base Family Catalog

File:

```text
config/base-family-catalog.example.json
```

Say:

```text
The family catalog is the control point. It maps scanner findings back to the
internal base lines platform owns, such as UBI plus OpenJDK, UBI plus Python, or
UBI plus NGINX. The upstream digest is pinned, so the workflow does not chase a
mutable latest tag.
```

## 4. Run The Planner

Command:

```bash
python3 scripts/plan_base_refresh_from_scan_metadata.py \
  examples/unique-images-for-refresh.example.json \
  examples/scan-metadata.example.json \
  config/base-family-catalog.example.json \
  /tmp/scotia-demo-plan

cat /tmp/scotia-demo-plan/family-refresh-summary.json
```

Expected output:

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

Say:

```text
The planner converted scanner events on running app images into family-level
refresh plans. This is the important behavior: we refresh the managed base
family once instead of doing one-off rebuild work for every affected app image.
```

Optional detail:

```bash
cat /tmp/scotia-demo-plan/family-refresh-plans.json
```

## 5. Dry-Run Upstream Acquisition

Command:

```bash
jq '.[2]' /tmp/scotia-demo-plan/family-acquisition-fanout.min.json > /tmp/scotia-demo-python-family.json

python3 scripts/refresh_base_family.py \
  /tmp/scotia-demo-python-family.json \
  /tmp/scotia-demo-python-acquire.json \
  --handoff-dir /tmp/scotia-demo-upstream-bases \
  --mode dry-run \
  --workflow-id demo

cat /tmp/scotia-demo-python-acquire.json
```

Say:

```text
This is dry-run mode. The worker validates the approved source, confirms the
upstream is digest-pinned, and prints the exact skopeo inspect/copy commands it
would run. It does not pull, push, rebuild, harden, or mutate anything.
```

Important fields to point at:

```text
status: dry-run
sourceReference: registry.redhat.io/...@sha256:...
corporateSafety.upstreamDigestRequired: true
corporateSafety.registryMutationAllowed: false
notes: no upstream image copy performed
```

## 6. Show The Helm Shape

Command:

```bash
helm lint helm/scotiabank-registry-remediator \
  --set namespace=registry-remediation \
  --set serviceAccount.name=registry-remediator \
  --set argo.pvc.claimName=registry-remediator-shared-work \
  --set argo.pvc.storageClassName=standard \
  --set schedule.cron="0 * * * *" \
  --set images.builder.repository=registry.corp/platform/skopeo-worker \
  --set images.builder.tag=approved
```

Optional render:

```bash
helm template smoke helm/scotiabank-registry-remediator \
  --show-only templates/workflowtemplate-remediate-image.yaml \
  --set namespace=registry-remediation \
  --set serviceAccount.name=registry-remediator \
  --set argo.pvc.claimName=registry-remediator-shared-work \
  --set argo.pvc.storageClassName=standard \
  --set schedule.cron="0 * * * *" \
  --set images.builder.repository=registry.corp/platform/skopeo-worker \
  --set images.builder.tag=approved
```

Say:

```text
The chart keeps the same parent/child Argo model: dedupe, plan from scanner
metadata, then fan out one minimal upstream acquisition payload per base family.
```

## 7. Close With Honest Production Gaps

Say:

```text
The production integration work is now clear: replace placeholder digests with
approved digests, wire real scanner metadata, use the approved skopeo worker
image and registry auth, connect the handoff path to the existing hardening
pipeline, and add state tracking to avoid repeat refresh storms.
```
