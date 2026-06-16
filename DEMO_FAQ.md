# Demo FAQ

This file is the plain-English guide for explaining the repo during a demo or
technical review. Use it when someone asks, "What does this repo actually do?"

## One-Sentence Pitch

This repo turns existing Trivy/Aqua findings plus the current `images.json`
runtime inventory into safe, deduplicated base-family refresh work.

It does not replace the scanner. It consumes scanner outputs and decides which
managed internal base image families need to be refreshed.

## Repo Layout

### Root Files

`README.md`

The high-level project explanation. It explains the goal, the end-to-end flow,
and why this is a registry-first base-image remediation design.

`DEMO.md`

The command-by-command demo script. Use this when presenting the local flow.

`DEMO_RUNBOOK.md`

An older but still useful runbook-style walkthrough for manually exercising the
pieces.

`WALKTHROUGH.md`

The broader system walkthrough. It explains the flow in more detail than the
README, especially how `images.json`, scan metadata, and base families connect.

`TRACKDOWN.md`

The list of questions and environment details to track down in Rancher,
Confluence, Bitbucket, registry settings, scanner config, and workflow config.

`DEMO_FAQ.md`

This file. It is optimized for answering questions in a live demo.

### `scripts/`

Local Python helper scripts. These are the source-of-truth versions used for
local testing.

`scripts/deduplicate_image_records.py`

Reads the current `images.json` runtime inventory, normalizes image references,
and collapses duplicate runtime sightings into unique images.

Inputs:

- `examples/collected-image-records.example.json`

Outputs:

- `unique-images.json`
- `unique-images.min.json`
- `sightings.json`
- `dedupe-summary.json`

Demo talking point:

"This prevents us from doing work per namespace or workload when the same image
is running in multiple places."

`scripts/trivy_to_scan_metadata.py`

Converts raw Trivy JSON into this repo's compact `scan-metadata/v1` contract.

Trivy already emits JSON, but raw Trivy JSON is scanner-specific and does not
contain all bank policy context. This adapter extracts vulnerability counts and
accepts additional context such as base family, base image lineage, and whether
the image uses a managed base.

Demo talking point:

"Trivy tells us what is vulnerable. The adapter adds the minimum platform
context the planner needs."

`scripts/filter_trivy_actionable.py`

Parses raw Trivy JSON and extracts actionable High/Critical findings. This is
useful for examples and policy experiments, but the main flow now expects compact
scan metadata from the existing scanner pipeline.

`scripts/plan_base_refresh_from_scan_metadata.py`

Joins three things:

- deduplicated running images
- compact scan metadata
- base-family catalog

It decides which vulnerable images should trigger a managed base-family refresh,
then groups the result into one plan per base family.

Outputs:

- `image-evaluations.json`
- `family-refresh-plans.json`
- `family-refresh-plans.min.json`
- `family-acquisition-fanout.min.json`
- `family-refresh-summary.json`

Demo talking point:

"The planner converts many image findings into a small number of base-family
actions."

`scripts/refresh_base_family.py`

Validates one base-family acquisition plan and either dry-runs or executes the
approved upstream acquisition step.

It enforces:

- allowed source types
- allowed registries
- digest-pinned upstream images by default
- no registry mutation from this step

It does not:

- add certificates
- harden images
- rebuild images
- rescan candidates
- publish final images
- mutate workloads

Demo talking point:

"This worker only grabs the approved upstream base and hands it off to the
existing cert/hardening pipeline."

### `examples/`

Demo data and generated example outputs.

`examples/collected-image-records.example.json`

Example production-shaped `images.json`. This is the running image inventory:
project, namespaces, and image references.

`examples/scan-metadata.example.json`

Compact scanner metadata in the expected `scan-metadata/v1` format.

`examples/trivy-report.example.json`

Example raw Trivy JSON.

`examples/trivy-scan-metadata.example.json`

Example output produced by `scripts/trivy_to_scan_metadata.py`.

`examples/unique-images-for-refresh.example.json`

Small input fixture used to demo the planner directly without first running the
dedupe step.

`examples/output/`

Checked-in example output from the dedupe script.

`examples/actionable-output/`

Checked-in example output from the Trivy actionable finding parser.

### `docs/`

Human-readable and machine-readable contracts.

`docs/architecture-flow.md`

Mermaid flow diagram for the overall architecture.

`docs/scan-metadata-input-schema.md`

Human-readable description of the compact scanner metadata contract.

`docs/scan-metadata.schema.json`

Machine-readable JSON Schema for `scan-metadata/v1`.

`docs/collected-image-record-schema.md`

Human-readable description of the running image inventory shape.

`docs/collected-image-record.schema.json`

Machine-readable schema for collected image records.

`docs/auth-and-secrets.md`

Notes about service accounts, registry credentials, scanner auth, Dex/LDAP, PVC
access, and what should not be copied into this chart.

`docs/trivy-reactive-registry-base-refresh.md`

Design notes for using Trivy findings to trigger registry-first base refreshes.

### `config/`

Local/demo config files.

`config/base-family-catalog.example.json`

Maps managed internal base families to approved upstream images and internal
publication targets.

Current example families:

- `ubi9-openjdk-17`
- `ubi9-python-311`
- `ubi9-nginx`

The digests are placeholders in the demo. In production, they must be replaced
with real approved digests.

`config/ownership-map.example.yaml`

Example ownership metadata. This is where team/contact style information can be
documented.

`config/source-locations.example.yaml`

Example source location metadata for `images.json`, scan metadata, and scanner
evidence paths.

### `helm/cluster-scan/`

The deployable Helm chart. This turns the scripts and config into Argo
WorkflowTemplates and Kubernetes ConfigMaps.

`Chart.yaml`

Helm chart metadata: name, description, type, and version.

`values.yaml`

The environment-specific settings. This is where the real cluster namespace,
service account, PVC, scanner output paths, worker images, registry allowlists,
and dry-run/execute mode are configured.

`templates/`

Kubernetes and Argo YAML templates. Helm renders these using `values.yaml`.

`files/`

Static files packaged into ConfigMaps. These are copies of scripts/config that
the running workflow pods mount at runtime.

Important convention:

- `scripts/*.py` are the local source versions.
- `helm/.../files/*.py` are the chart-packaged versions.
- Keep matching script pairs synchronized.

## Helm Flow

The Helm chart installs several resources.

### ConfigMaps

Defined in:

- `helm/cluster-scan/templates/configmap-metadata.yaml`

They package scripts and example config into the cluster so workflow pods can
mount them.

Important ConfigMaps:

- `cluster-scan-dedupe-script`
- `cluster-scan-metadata-planner-script`
- `cluster-scan-refresh-base-family-script`
- `cluster-scan-family-catalog`
- `cluster-scan-ownership`
- `cluster-scan-sources`

### Shared PVC

Defined in:

- `helm/cluster-scan/templates/pvc-shared-data.yaml`

Purpose:

- hold `images.json`
- hold `scan-metadata.json`
- share intermediate outputs between child workflows
- hold upstream base handoff output

Default mount path:

```text
/work/shared
```

### Inventory Dedupe WorkflowTemplate

Defined in:

- `helm/cluster-scan/templates/workflowtemplate-inventory-dedup.yaml`

Reads:

- `/work/shared/images.json`

Writes:

- `/work/shared/dedupe-output/unique-images.json`
- `/work/shared/dedupe-output/sightings.json`
- `/work/shared/dedupe-output/dedupe-summary.json`

### Scan Metadata Planner WorkflowTemplate

Defined in:

- `helm/cluster-scan/templates/workflowtemplate-scan-metadata-planner.yaml`

Reads:

- `/work/shared/dedupe-output/unique-images.json`
- `/work/shared/scan-metadata.json`
- `/opt/remediator/catalog/base-family-catalog.example.json`

Writes:

- `/work/shared/refresh-plan/image-evaluations.json`
- `/work/shared/refresh-plan/family-refresh-plans.json`
- `/work/shared/refresh-plan/family-acquisition-fanout.min.json`
- `/work/shared/refresh-plan/family-refresh-summary.json`

### Refresh Base Family WorkflowTemplate

Defined in:

- `helm/cluster-scan/templates/workflowtemplate-remediate-image.yaml`

Despite the filename saying `remediate-image`, the actual Kubernetes object is:

```text
cluster-scan-refresh-base-family
```

It takes one family plan from the planner fanout and runs
`refresh_base_family.py`.

Default mode:

```text
dry-run
```

In execute mode, this step uses `skopeo` to copy an approved upstream image into
an OCI handoff directory.

### Orchestrator WorkflowTemplate

Defined in:

- `helm/cluster-scan/templates/workflowtemplate-orchestrator.yaml`

Runs the child workflows in this order:

1. `inventory-dedup`
2. `plan-family-refreshes`
3. `refresh-each-family`

The final step uses Argo `withParam` to fan out once per base family from:

```text
family-acquisition-fanout.min.json
```

### CronWorkflow

Defined in:

- `helm/cluster-scan/templates/cronworkflow-scheduled.yaml`

Purpose:

- optionally run the orchestrator on a schedule

This is controlled by:

```text
schedule.cron
```

## Naming Conventions

### `cluster-scan-*`

Prefix for Kubernetes resources owned by this chart.

Examples:

- `cluster-scan-orchestrator`
- `cluster-scan-inventory-dedup`
- `cluster-scan-scan-metadata-planner`

### `base-family`

A managed internal base image line owned by platform engineering.

Examples:

- `ubi9-openjdk-17`
- `ubi9-python-311`
- `ubi9-nginx`

### `family-refresh`

The decision that a base family should be refreshed because one or more running
images using that family have actionable scanner findings.

### `family-acquisition`

The smaller handoff plan that says:

- which family
- which approved upstream image
- which pinned digest

This is what the Argo fanout uses.

### `metadata`

Small JSON facts used for planning. In this repo, metadata means compact scanner
summaries, not full image tarballs.

### `.min.json`

Compact JSON intended for Argo parameters or small control-plane handoffs.

Full JSON files are kept as artifacts for review and audit.

## Why We Need The Trivy Adapter

Trivy already emits JSON. The adapter is still useful because raw Trivy JSON and
remediation planning JSON are different contracts.

Trivy tells us:

- CVE IDs
- severity
- package names and versions
- fixed versions
- target paths or package classes

The planner also needs platform context:

- which running image was scanned
- image digest
- whether this image uses a managed base
- which base family it maps to
- which base image lineage was detected
- where the report/evidence lives

Trivy does not inherently know bank-approved base lineage. That context must
come from labels, registry/build metadata, source repo enrichment, or the
base-family catalog.

The adapter gives the existing scanner workflow a clean way to emit the compact
contract expected by this repo:

```text
raw Trivy JSON + platform context -> scan-metadata/v1
```

## Is This Plug And Play With The Existing Scanner Chart?

Not completely, but the integration boundary is intentionally small.

The existing environment must provide:

- `images.json`
- compact `scan-metadata.json`
- access to a shared PVC or object-store handoff
- service account/RBAC
- registry credentials
- approved base-family catalog entries
- worker image with `python3` and `skopeo`

The existing scanner chart can integrate in either of two ways.

Option A: scanner chart writes `scan-metadata/v1` directly.

This is the cleanest long-term design.

Option B: scanner chart writes raw Trivy JSON, then runs this adapter as a
post-processing step.

This is easier if the scanner team already owns the Trivy command and only wants
to add a small transformation step.

## Questions To Expect

### Does this rescan every running image?

No. It consumes existing scanner metadata. The current repo does not rescan all
running images after reading `images.json`.

### What does `images.json` do?

It defines runtime scope. It tells us what is actually running, so remediation
planning stays tied to real blast radius.

### What does `scan-metadata.json` do?

It provides vulnerability signal and enough platform context to map findings to
base-family refresh work.

### Why not rebuild the vulnerable app image directly?

Because the controlled platform-owned unit is usually the internal base family.
Refreshing the base family once is safer and more reusable than creating one-off
app image mutations.

### How does the system know an image is corporate-safe?

It does not trust "latest." The family catalog must point to approved upstream
sources, and `refresh_base_family.py` requires digest-pinned upstreams from
allowlisted source types and registries.

### What currently prevents accidental mutation?

The default mode is `dry-run`. The acquisition worker also blocks unpinned
upstreams and non-allowlisted registries by default.

### Does this push images?

No. Not in the current scaffold. It only plans refreshes and dry-runs or performs
approved upstream acquisition into a handoff location.

### Where do cert injection and hardening happen?

Outside this scaffold, in the existing process. This repo explicitly stops at
the upstream acquisition handoff.

### Why are there duplicate scripts under `scripts/` and `helm/.../files/`?

`scripts/` is for local development and testing. `helm/.../files/` is what Helm
packages into ConfigMaps so workflow pods can run the same logic in-cluster.

### What should be replaced before production?

- placeholder namespace
- service account
- PVC/storage class
- worker images
- registry credentials
- Red Hat/internal registry paths
- placeholder upstream digests
- real base-family catalog
- scanner metadata handoff location
- post-acquisition cert/hardening integration
- candidate rescan and publication gates

### What is the biggest integration risk?

Base image lineage. If the scanner pipeline cannot tell us `baseFamily` or
`managedBaseImage`, we need an enrichment step using labels, registry metadata,
Dockerfile provenance, or the base-family catalog.

### What is safe to demo now?

- dedupe of `images.json`
- Trivy raw JSON to compact metadata
- metadata-driven refresh planning
- family-level fanout
- dry-run approved upstream acquisition
- blocked unsafe upstream examples

### What should not be claimed yet?

- production publication
- automatic cert injection
- full hardening
- final candidate image signing
- live registry mutation
- complete integration with the existing scanner chart

## Good Demo Language

"This is not a second scanner. It is the remediation control plane that consumes
the scanner's output."

"`images.json` tells us what is running. `scan-metadata.json` tells us what is
vulnerable. The base-family catalog tells us what platform-owned base line to
refresh."

"We fan out by base family, not by every vulnerable image sighting."

"The current worker is intentionally conservative: dry-run by default,
digest-pinned upstreams, allowlisted registries, and no cluster mutation."

"The major integration item is lineage: we need the existing scanner workflow or
an enrichment step to tell us whether a vulnerable image is based on a managed
internal base family."
