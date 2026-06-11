# Project Walkthrough

This repo is a scaffold and demo for a registry-first base image remediation flow.
It does not replace the existing scanner platform. It consumes scanner outputs and
turns them into family-level upstream acquisition work.

## The Short Version

The flow is:

1. Existing image dump/scanner pipeline writes `images.json`.
2. Existing Aqua/Trivy pipeline writes compact scan metadata.
3. This repo deduplicates running images from `images.json`.
4. It joins those images to scanner metadata.
5. It maps vulnerable images to managed base families like `ubi9-openjdk-17`.
6. It creates one refresh plan per impacted base family.
7. It dry-runs acquisition of the approved upstream base image by digest.
8. Existing cert injection, hardening, rebuild, verification, and publishing take over later.

## Core Inputs

### `images.json`

Expected location in the chart:

```text
/work/shared/images.json
```

Configured in:

```text
helm/scotiabank-registry-remediator/values.yaml
```

This file should contain all running image references for the cluster/environment
scope being remediated. If an image is not in this file, this platform will not
dedupe it, match it to scan metadata, or plan a base-family refresh for it.

Example shape:

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

Important files:

```text
examples/collected-image-records.example.json
docs/collected-image-record-schema.md
docs/collected-image-record.schema.json
```

### Scan Metadata

Expected location in the chart:

```text
/work/shared/scan-metadata.json
```

Configured in:

```text
helm/scotiabank-registry-remediator/values.yaml
```

This is compact scanner output from Aqua/Trivy. It should include image identity,
High/Critical counts, fixable counts, target classes, managed-base signal, and
ideally `baseFamily`.

Important files:

```text
examples/scan-metadata.example.json
docs/scan-metadata-input-schema.md
```

## Base Families

A base family is a managed internal base line your platform team owns. Examples:

```text
ubi9-openjdk-17
ubi9-python-311
ubi9-nginx
```

The family catalog says:

- how to recognize the family
- what approved upstream source image should be acquired
- what internal publication target eventually belongs to it
- what verification policy should apply downstream

Important files:

```text
config/base-family-catalog.example.json
helm/scotiabank-registry-remediator/files/base-family-catalog.example.json
```

The current example catalog includes:

```text
registry.redhat.io/ubi9/openjdk-17-runtime
registry.redhat.io/ubi9/python-311
registry.redhat.io/ubi9/nginx-124
```

The digests are placeholders. For real use, replace them with corporate-approved
pinned digests.

## Python Scripts

### `scripts/deduplicate_image_records.py`

Purpose:

- accepts the nested `images.json` format or an expanded record array
- normalizes image references
- collapses repeated sightings into unique runtime artifacts
- preserves sighting metadata for impact reporting

Inputs:

```text
examples/collected-image-records.example.json
```

Outputs:

```text
unique-images.json
unique-images.min.json
sightings.json
dedupe-summary.json
```

Demo command:

```bash
python3 scripts/deduplicate_image_records.py \
  examples/collected-image-records.example.json \
  /tmp/scotia-demo-dedupe
```

### `scripts/plan_base_refresh_from_scan_metadata.py`

Purpose:

- reads deduplicated runtime images
- reads compact scan metadata
- reads the family catalog
- decides which images should trigger base-family refresh planning
- groups many vulnerable app images into one plan per base family

Automatic refresh planning requires:

- High or Critical findings exist
- at least one High or Critical finding is fixable
- target class looks like base/runtime work, such as `rhel-base`, `jdk-runtime`, `python-runtime`, or `nginx`
- scanner metadata does not mark the image as unmanaged
- the image maps to a known family

Demo command:

```bash
python3 scripts/plan_base_refresh_from_scan_metadata.py \
  examples/unique-images-for-refresh.example.json \
  examples/scan-metadata.example.json \
  config/base-family-catalog.example.json \
  /tmp/scotia-demo-plan
```

Expected summary:

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

### `scripts/refresh_base_family.py`

Purpose:

- validates one family refresh plan
- enforces approved upstream source type and registry allowlists
- requires digest-pinned upstreams by default
- dry-runs or executes a `skopeo` copy into an OCI handoff directory

It does not:

- add certificates
- harden images
- build images
- scan candidates
- push final images
- mutate running clusters

In execute mode, the intended command shape is:

```bash
skopeo inspect docker://registry.redhat.io/ubi9/python-311@sha256:<approved-digest>
skopeo copy docker://registry.redhat.io/ubi9/python-311@sha256:<approved-digest> \
  oci:/work/shared/upstream-bases/ubi9-python-311/<run-id>:upstream
```

### `scripts/filter_trivy_actionable.py`

Purpose:

- takes raw Trivy JSON
- keeps policy-relevant High/Critical findings
- marks findings actionable when a fixed version and target classification exist

This is useful as an example parser, but the main redesign assumes the existing
scanner stack already emits compact scan metadata.

## Helm Chart

Chart directory:

```text
helm/scotiabank-registry-remediator
```

### `Chart.yaml`

Basic chart metadata.

### `values.yaml`

All environment-specific placeholders live here:

- namespace
- service account
- PVC name, storage class, size
- scanner input paths
- workflow output paths
- worker images
- approved upstream source controls
- CronWorkflow schedule

The default `refreshBaseFamily.mode` is:

```yaml
mode: dry-run
```

That is intentional. The chart should not acquire or mutate anything by default.

### `templates/configmap-metadata.yaml`

Packages helper scripts and example config into ConfigMaps:

- dedupe script
- metadata planner script
- upstream acquisition script
- source locations example
- ownership map example
- family catalog example

This keeps the Argo workflows self-contained for the demo.

### `templates/workflowtemplate-inventory-dedup.yaml`

Argo child workflow:

```text
images.json -> unique-images.json + sightings.json + dedupe-summary.json
```

It mounts the shared PVC at `/work/shared` and expects:

```text
/work/shared/images.json
```

### `templates/workflowtemplate-scan-metadata-planner.yaml`

Despite the filename, this is currently the scan metadata planner template.

Argo child workflow:

```text
unique-images.json + scan-metadata.json + base-family-catalog.json
  -> image-evaluations.json
  -> family-refresh-plans.json
  -> family-acquisition-fanout.min.json
  -> family-refresh-summary.json
```

### `templates/workflowtemplate-remediate-image.yaml`

This is the `refresh-base-family` child workflow.

Current responsibility:

```text
one family plan -> approved upstream acquisition dry-run/output
```

It calls:

```text
/opt/remediator/refresh_base_family.py
```

It does not do the downstream cert/hardening/rebuild/publish work.

### `templates/workflowtemplate-orchestrator.yaml`

Parent workflow:

```text
inventory-dedup
  -> plan-family-refreshes
  -> refresh-each-family fan-out
```

The fan-out is one minimal family/upstream payload per base family, not one item
per vulnerable app image. The full `family-refresh-plans.json` remains available
as an audit artifact with impact and evidence context.

### `templates/cronworkflow-scheduled.yaml`

Optional scheduled trigger for the orchestrator.

The schedule is a placeholder in:

```text
helm/scotiabank-registry-remediator/values.yaml
```

### `templates/pvc-shared-data.yaml`

Optional shared PVC for handoff files between workflow steps.

Configured by:

```yaml
argo:
  pvc:
    enabled: true
    claimName: ...
    mountPath: /work/shared
    storageClassName: ...
    size: 20Gi
```

## Safety Controls

The upstream acquisition worker currently enforces:

- dry-run by default
- approved source types only
- approved upstream registries only
- digest-pinned upstream references by default
- no registry mutation flag in dry-run output
- no cert/hardening/rebuild/publish behavior

Current defaults:

```yaml
refreshBaseFamily:
  mode: dry-run
  allowedUpstreamSourceTypes:
    - redhat-catalog
    - internal-approved-registry
  allowedUpstreamRegistries:
    - registry.redhat.io
  allowUnpinnedApprovedUpstream: false
```

The allowlist is a guardrail, not a full approval process. Real approval comes
from replacing placeholder digests with corporate-approved pinned digests.

## Demo Commands

Run the local script flow:

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

Dry-run upstream acquisition for all planned families:

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
```

Helm validation with realistic values:

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

## What Is Solid For Demo

- The Python data flow runs locally.
- The planner produces one plan per family.
- The upstream acquisition worker defaults to dry-run.
- The chart renders and lints when realistic placeholder overrides are supplied.
- The chart does not intentionally mutate clusters, push images, or rebuild images.

## What Is Still Placeholder Or Production Integration

- Real corporate-approved digests.
- Real `images.json` from the current image dump pipeline.
- Real scan metadata from Aqua/Trivy.
- Real Argo namespace, service account, PVC, storage class, and schedule.
- Approved worker image containing `python3`, `skopeo`, and required registry auth setup.
- Connection from `/work/shared/upstream-bases` to the existing cert/hardening/rebuild process.
- Candidate verification and publish gates.
- State tracking to avoid repeated refresh storms for the same family.

## Review Checklist

Before showing this at work, review:

- `README.md`
- `DEMO_RUNBOOK.md`
- `config/base-family-catalog.example.json`
- `examples/scan-metadata.example.json`
- `scripts/plan_base_refresh_from_scan_metadata.py`
- `scripts/refresh_base_family.py`
- `helm/scotiabank-registry-remediator/values.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-orchestrator.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-inventory-dedup.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-scan-metadata-planner.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-remediate-image.yaml`
