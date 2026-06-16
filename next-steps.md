# cluster-scan — next steps

## What is done right now

The nightly runtime scanning/reporting path is now split cleanly from base-image rebuild automation.

Implemented and verified:
- chart/workflow naming switched from `scotiabank-registry-remediator` to `cluster-scan`
- runtime inventory keeps richer context:
  - cluster
  - namespace
  - workload kind
  - workload name
  - pod name
  - container name
  - container type
  - app labels when available (`appName`, `appInstance`, `component`, `partOf`, `managedBy`)
- dedupe still scans each unique image once, but preserves runtime sightings for reverse-join reporting
- reporting merge now outputs:
  - `runtime-artifacts.json`
  - `cluster-runtime-vulnerability-report.json`
  - `workload-vulnerability-dashboard.json`
  - `application-vulnerability-dashboard.json`
  - `runtime-vulnerability-summary.json`
- dark-mode native HTML dashboard now renders from reporting JSON and includes JSON download links
- Argo chart now includes dashboard rendering in the runtime reporting workflow

## What I tested

### Unit / local verification
Commands run:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall scripts tests
helm lint helm/cluster-scan
helm template smoke helm/cluster-scan --set argo.pvc.claimName=cluster-scan-shared >/tmp/cluster-scan-rendered.yaml
```

Results:
- unit tests: passed
- compile check: passed
- helm lint: passed with one expected placeholder warning for the PVC name default
- helm template smoke: passed

### End-to-end dry run of the reporting flow
I also ran a local E2E simulation of the nightly flow using synthetic per-cluster inventory plus matching scan metadata:

```bash
python3 scripts/deduplicate_image_records.py /tmp/cluster-scan-e2e/inventory /tmp/cluster-scan-e2e/output
python3 scripts/build_runtime_vulnerability_reports.py \
  /tmp/cluster-scan-e2e/output/unique-images.json \
  /tmp/cluster-scan-e2e/output/sightings.json \
  /tmp/cluster-scan-e2e/scan/scan-metadata.json \
  /tmp/cluster-scan-e2e/report
python3 scripts/render_runtime_dashboard.py /tmp/cluster-scan-e2e/report /tmp/cluster-scan-e2e/report/index.html
```

Verified from the generated artifacts:
- summary contained:
  - `clusterCount = 2`
  - `workloadCount = 4`
  - `applicationCount = 2`
  - `containersWithHighOrCritical = 3`
- per-app rollup worked:
  - app `payments` resolved to 3 workload entries across 2 clusters
- per-workload rollup worked:
  - `CronJob/payments-settlement` had its own workload row and vuln summary
- dashboard HTML rendered and exposed download buttons for all JSON artifacts

## Why the merge logic now makes sense

The reporting logic is now intentionally two-stage:

1. **scan-efficient stage**
   - dedupe runtime image sightings
   - scan each unique image exactly once

2. **dashboard-accurate stage**
   - join scan results back to every runtime sighting
   - rebuild views by cluster, workload, and app

That gives us both things we actually need:
- sane Trivy cost/performance
- a dashboard that is not lying about blast radius

### Current grouping behavior

#### Per workload
A workload row is keyed by:
- cluster
- namespace
- workload kind
- workload name

That means the same app deployed in two clusters shows up as two workload rows, which is correct for runtime operations.

#### Per app
An app rollup is keyed primarily by:
- `appName` from Kubernetes labels when available
- fallback to workload name when labels are absent

That means:
- cluster-level runtime operations stay precise
- app-level dashboarding still gets a cleaner cross-cluster rollup

## Implementation steps — recommended next

### 1. Add real cluster metadata and label discipline
Why:
- app rollups are only as good as runtime labels
- if teams don’t label workloads consistently, the app dashboard becomes fallback-name soup

Do:
- standardize required labels for scanned workloads:
  - `app.kubernetes.io/name`
  - `app.kubernetes.io/instance`
  - `app.kubernetes.io/component`
  - `app.kubernetes.io/part-of`
  - `app.kubernetes.io/managed-by`
- document those as the contract for cluster-scan ingestion
- reject or flag unlabeled workloads in a future “data quality” report

### 2. Add vuln trend/history storage
Why:
- one nightly snapshot is nice
- trends are what make leadership and platform people actually care

Do:
- persist nightly outputs by date, for example:
  - `runtime-reporting/YYYY-MM-DD/runtime-vulnerability-summary.json`
  - `runtime-reporting/YYYY-MM-DD/application-vulnerability-dashboard.json`
- add a small history index JSON
- later show trend lines for:
  - total vulnerable containers
  - vulnerable apps
  - high/critical counts
  - fixable high/critical counts

### 3. Add data quality and scan coverage checks
Why:
- the easiest way to get embarrassed is to present a clean dashboard that is silently incomplete

Do:
- emit a coverage report with:
  - total unique runtime images
  - scanned unique images
  - unscanned images
  - workloads missing app labels
  - clusters skipped / failed
- make the dashboard clearly show partial-data states

### 4. Add severity and ownership filters to the HTML dashboard
Why:
- right now it is solid and usable
- next step is making it genuinely good for triage

Do:
- add filters for:
  - owner team
  - cluster
  - namespace
  - app
  - severity presence
  - fixable only
- add sort options:
  - most exposed apps
  - most critical findings
  - largest blast radius by cluster/workload

### 5. Add drill-down details per workload/app
Why:
- the top-level cards are good
- triage still needs faster “tell me exactly what to fix” paths

Do:
- expandable rows or detail panes showing:
  - containers
  - images
  - vuln counts
  - Trivy report links
  - base family
  - scanner timestamp
- add explicit “copy canonical key” / “copy image reference” actions later if needed

### 6. Add CSV export for management/reporting consumers
Why:
- some stakeholders will ask for spreadsheets because suffering must continue

Do:
- export CSV views for:
  - vulnerable workloads
  - vulnerable apps
  - vulnerable images
  - cluster summary

### 7. Add failure-tolerant nightly workflow behavior
Why:
- one broken cluster auth context should not nuke the entire nightly run

Do:
- isolate per-cluster collection failures
- produce partial output plus failure summary
- keep successful cluster results
- surface failed clusters in dashboard + summary artifact

### 8. Add provenance fields to every artifact
Why:
- people will absolutely ask “when did this scan happen?” and “which run produced this?”

Do:
- stamp outputs with:
  - workflow run id
  - collection timestamp
  - scan timestamp
  - source cluster config version
  - renderer version

### 9. Add a proper nightly `CronWorkflow` deployment profile
Why:
- right now the runtime workflow shape is there
- we still need a clean real env profile for the actual nightly schedule

Do:
- create a deployment values file specifically for runtime scanning
- wire:
  - cluster config source
  - scan output retention path
  - dashboard publishing path
  - secrets / registry auth / kube contexts

### 10. Later: evaluate Airflow only if orchestration requirements actually justify it
Why:
- for pure nightly scanning, Argo is still perfectly fine right now
- adding Airflow too early is how you accidentally create extra architecture cosplay

Use Airflow later if you need:
- DAG-style retries and backfills across many reporting stages
- stronger scheduling / dependency management across multiple data products
- integration with a wider reporting/data platform

Do **not** move to Airflow yet just because it sounds enterprise-y.
The current bottleneck is data quality, scan coverage, and dashboard usefulness — not orchestration brand selection.

## Suggested immediate order of attack

If I were sequencing this sanely:

1. enforce app/workload label quality
2. add scan coverage + failed-cluster reporting
3. add dashboard filters and drill-downs
4. add historical snapshot retention + trend view
5. add CSV export
6. only then revisit Airflow

## Files touched for this phase

Core scripts:
- `scripts/collect_cluster_images.py`
- `scripts/deduplicate_image_records.py`
- `scripts/build_runtime_vulnerability_reports.py`
- `scripts/render_runtime_dashboard.py`

Tests:
- `tests/test_collect_cluster_images.py`
- `tests/test_deduplicate_image_records.py`
- `tests/test_build_runtime_vulnerability_reports.py`

Chart:
- `helm/cluster-scan/Chart.yaml`
- `helm/cluster-scan/values.yaml`
- `helm/cluster-scan/templates/configmap-metadata.yaml`
- `helm/cluster-scan/templates/workflowtemplate-orchestrator.yaml`
- `helm/cluster-scan/templates/workflowtemplate-build-runtime-report.yaml`
- `helm/cluster-scan/templates/workflowtemplate-base-rebuild-automation.yaml`

## Blunt assessment

The core shape is good now.
The important thing is that it finally behaves like a runtime visibility/reporting product instead of a confused half-scanner half-remediator blob.

What will make this impressive is not more buzzwords.
It will be:
- trustworthy coverage
- clean rollups
- obvious blast radius
- useful visuals
- stable nightly operation
