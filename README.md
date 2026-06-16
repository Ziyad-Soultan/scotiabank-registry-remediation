# cluster-scan Runtime Vulnerability Platform

## What this repo does now
The repo is split into **two separate flows** because the scope changed again, because of course it did.

### 1. Base-image rebuild automation
This flow is for the **base image repo** path.

That repo already has:
- its own scanning
- its own smoke tests

So this repo should **not** pretend to own that detection logic anymore.
It only owns the automation that starts once a base-family rebuild is already justified.

**This flow now does:**
1. accept one approved `family-plan` JSON payload
2. validate the upstream source and digest policy
3. acquire/copy the approved upstream base image
4. hand the result to the rebuild/cert/hardening contract

**Primary Argo entrypoint:**
- `cluster-scan-base-rebuild-automation`

**Core worker/template:**
- `cluster-scan-refresh-base-family`

### 2. Nightly runtime vulnerability reporting
This flow is for **everything currently running on clusters every night**.

It is completely separate from rebuild automation.
It does **not** trigger family rebuilds.
It ends in reporting artifacts for dashboards and vulnerability review.

**This flow now does:**
1. collect runtime inventory from clusters
2. dedupe repeated runtime image sightings
3. scan each unique runtime image with Trivy once
4. merge scan results back with sightings
5. emit cluster/workload/app/dashboard JSON outputs and a dark-mode HTML dashboard

**Primary Argo entrypoint:**
- `cluster-scan-orchestrator`

## Why the split matters
Before, the repo was mixing two different jobs:
- *runtime visibility/reporting*
- *base-family rebuild automation*

Those are related, but they are not the same thing.

If you keep them glued together, you get garbage behavior:
- runtime dashboard work starts mutating rebuild queues
- rebuild flow becomes coupled to cluster inventory timing
- reporting artifacts get buried inside remediation logic
- every scope change forces another stupid architectural rewrite

So the repo now treats them as separate products that can still share helper code where useful.

---

## Flow A: base-image rebuild automation

### Goal
Automate the part that is currently:
> go find the approved upstream base, copy it, add org stuff, rebuild, publish

### Inputs
One family plan JSON object, typically shaped like:

```json
{
  "family": "ubi9-openjdk-17",
  "upstream": {
    "sourceType": "redhat-catalog",
    "image": "registry.redhat.io/ubi9/openjdk-17-runtime",
    "digest": "sha256:..."
  },
  "publication": {
    "targetRepository": "registry.corp/base/ubi9-openjdk-17"
  }
}
```

### Outputs
- upstream acquisition JSON
- rebuild handoff JSON

### Relevant files
- `scripts/refresh_base_family.py`
- `scripts/rebuild_family_candidate.py`
- `helm/cluster-scan/templates/workflowtemplate-remediate-image.yaml`
- `helm/cluster-scan/templates/workflowtemplate-base-rebuild-automation.yaml`

### Important rule
This flow is **not** driven by nightly cluster scans anymore.
If the base-image repo decides a family should rebuild, it calls this flow directly.

---

## Flow B: nightly runtime vulnerability reporting

### Goal
Produce a complete view of:
- what is running on clusters
- which images are used where
- what each image's Trivy results are
- which apps/workloads/clusters are currently exposed

### Runtime reporting pipeline

#### 1. Collect runtime inventory
Script:
- `scripts/collect_cluster_images.py`

The collector now preserves more than just image strings.
It keeps runtime context like:
- cluster
- namespace
- workload kind
- workload name
- pod name
- container name
- container type

That matters because a dashboard that only says *"some namespace used this image once"* is basically decorative nonsense.

#### 2. Dedupe runtime artifacts
Script:
- `scripts/deduplicate_image_records.py`

Outputs:
- `unique-images.json`
- `unique-images.min.json`
- `sightings.json`
- `dedupe-summary.json`

This keeps scan cost sane by scanning one unique image once, while preserving every place it was seen.

#### 3. Scan each unique image once with Trivy
Script:
- `scripts/scan_unique_images.py`

Output:
- `scan-metadata.json`

This remains artifact-centric on purpose.
One image, one scan. Not one scan per workload sighting like some kind of compute-burning ritual sacrifice.

#### 4. Re-consolidate sightings with scan results
Script:
- `scripts/build_runtime_vulnerability_reports.py`

Outputs:
- `runtime-artifacts.json`
- `cluster-runtime-vulnerability-report.json`
- `workload-vulnerability-dashboard.json`
- `application-vulnerability-dashboard.json`
- `runtime-vulnerability-summary.json`
- `index.html`

This is the missing piece you called out correctly:
**dedupe is good for scanning, but reporting needs the sightings merged back in**.

That merge step is what makes the dashboard comprehensive again.

### Dashboard/reporting data model
The reporting flow now gives you two useful views:

#### Cluster view
Nested by:
- cluster
- namespace
- workload
- container
- image
- scan summary

This answers:
- what is running on each cluster?
- which containers are exposed?
- how many high/critical findings are tied to each runtime image?

#### Application view
Aggregated by workload/app.

This answers:
- what images does this app use?
- in which clusters/namespaces does it run?
- which of its containers/images currently carry high/critical findings?

---

## Argo workflow shape

### Runtime reporting flow
Top-level workflow:
- `cluster-scan-orchestrator`

Steps:
1. `collect-cluster-images`
2. `inventory-dedup`
3. `scan-unique-images`
4. `build-runtime-report`

### Base rebuild automation flow
Top-level workflow:
- `cluster-scan-base-rebuild-automation`

Delegates to:
- `refresh-base-family`

---

## Helm/chart changes
The chart now includes:
- runtime reporting merge workflow template
- base rebuild automation wrapper workflow template
- runtime reporting script ConfigMap
- runtime dashboard renderer script + HTML artifact output
- runtime reporting output directory in values
- updated orchestrator that ends in reporting, not refresh fan-out

Relevant templates:
- `templates/workflowtemplate-orchestrator.yaml`
- `templates/workflowtemplate-build-runtime-report.yaml`
- `templates/workflowtemplate-base-rebuild-automation.yaml`
- `templates/workflowtemplate-remediate-image.yaml`
- `templates/configmap-metadata.yaml`

Relevant values:
- `workflowPaths.runtimeReportingOutputDir`
- `schedule.cron` for nightly runtime reporting

---

## Scripts summary

### Runtime reporting
- `scripts/collect_cluster_images.py`
- `scripts/deduplicate_image_records.py`
- `scripts/scan_unique_images.py`
- `scripts/build_runtime_vulnerability_reports.py`
- `scripts/trivy_to_scan_metadata.py`
- `scripts/filter_trivy_actionable.py`

### Base rebuild automation
- `scripts/refresh_base_family.py`
- `scripts/rebuild_family_candidate.py`

### Optional helper still present
- `scripts/plan_base_refresh_from_scan_metadata.py`

That planner is still here as a helper if you ever want to translate scan metadata into family plans, but it is **no longer part of the default nightly reporting path**.

---

## Testing
Current unit tests cover:
- runtime inventory collection with workload/container preservation
- dedupe expansion preserving runtime context
- scan/report merge into cluster and app views

Test files:
- `tests/test_collect_cluster_images.py`
- `tests/test_deduplicate_image_records.py`
- `tests/test_scan_unique_images.py`
- `tests/test_build_runtime_vulnerability_reports.py`

Run with:

```bash
python3 -m unittest discover -s tests -v
```

---

## Practical outcome
If someone asks *"what does this repo own now?"*, the answer is finally clean:

### It owns
- nightly runtime inventory + Trivy reporting for running cluster images
- rebuild automation once a base-family rebuild decision already exists

### It does not own
- the base-image repo's existing scan/smoke-test logic
- automatic coupling from nightly runtime findings straight into rebuild actions

Which is good, because that coupling would have been architectural glue-sniffing.
