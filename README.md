# Scotiabank Registry Remediation Platform Scaffold

## Goal
Extend the existing cluster image inventory + Aqua/Trivy reporting stack into a **registry-first internal base image refresh platform**.

This scaffold assumes the current environment already produces:
- a running image inventory file (for example `images.json` from the cluster image dump agent)
- scanner metadata and reports from the existing Aqua/Trivy workflow

Instead of rescanning or archiving every image again, this repo focuses on:
1. consuming the existing runtime image list,
2. deduplicating it into unique runtime artifacts,
3. consuming compact scanner metadata,
4. deciding which managed internal base families actually need refresh,
5. rebuilding only those internal base images,
6. rescanning candidates,
7. publishing refreshed base images back to the internal registry.

## The system in one sentence
Use existing scanner findings as the **trigger**, but perform remediation at the **managed internal base-family level**.

That is the whole trick.

## Why this redesign exists
The current scan/reporting stack already does the expensive detection work:
- inventory collection
- scan execution
- result parsing
- reporting/dashboard output

So the remediation platform should not behave like a needy middle manager and duplicate all of that.

It should reuse:
- the list of running images
- compact vulnerability metadata
- existing evidence/report links

Then it should do the missing operational action:
- resolve impacted images back to managed internal base families,
- rebuild those families from approved upstream sources,
- apply org customization,
- publish refreshed candidates internally.

## What changed in this repo
This scaffold is now built around the **existing scanner outputs** instead of around a brand-new full-image scanning pipeline.

### The major architectural change
Old shape:
- collect image list
- scan each unique image here
- classify findings here
- remediate image here

New shape:
- ingest the running image list from the existing stack
- dedupe runtime artifacts here
- ingest compact scan metadata from the existing stack
- plan family refreshes here
- rebuild only the internal managed base families that need action

## End-to-end walkthrough
If you need to explain the full system to another engineer, use this sequence.

### 1. Existing scanner stack produces running image inventory
The current cluster image dump / Aqua workflow already emits the runtime image list.

Typical source:
- `images.json`
- object store path or PVC handoff

This repo expects that `images.json` is the complete running-image inventory for the
cluster or environment scope being remediated. If a running image is missing from
that file, this platform will not include it in dedupe, scanner metadata matching,
or family refresh planning.

Current known shape:

```json
{
  "epm_code": "gpedev",
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

**Purpose:**
Define what is actually running in clusters.

**Why it is needed:**
If it is not running, it is not part of the immediate blast radius.

**How it plugs in:**
This becomes the input to the dedupe child workflow. The dedupe script now expands this nested format automatically, so no pre-conversion step is required.

### 2. Existing scanner stack produces vulnerability metadata
The current Aqua/Trivy workflow also produces scan metadata and reports.

Preferred inputs for this repo:
- compact JSON metadata summaries
- optional HTML/CSV evidence links

Avoid relying on:
- full image archives
- giant duplicated raw blobs unless absolutely necessary

**Purpose:**
Provide vulnerability signal without forcing this repo to redo the scanner's job.

**Why it is needed:**
Storage and compute get stupid fast if every downstream workflow re-archives every image again.

**How it plugs in:**
This becomes the input to the metadata-planning child workflow.

### 3. Child workflow: inventory-dedup
This child reads the `images.json` running image inventory and converts repeated sightings into:
- `unique-images.json`
- `sightings.json`
- `dedupe-summary.json`

**Purpose:**
Separate one unique runtime artifact from many impacted workloads.

**Why it is needed:**
If 20 workloads use the same digest, planning 20 separate remediations is brain-dead.

**How it plugs in:**
The planner uses `unique-images.json` as the runtime artifact set.

### 4. Child workflow: plan-refresh-from-scan-metadata
This child reads:
- `unique-images.json`
- existing scanner metadata JSON
- the internal base-family catalog

It emits:
- `image-evaluations.json`
- `family-refresh-plans.json`
- `family-acquisition-fanout.min.json`
- `family-refresh-summary.json`

**Purpose:**
Convert scanner findings into deduplicated internal base-family refresh work.

**Why it is needed:**
The scanner tells you something is vulnerable.
It does **not** tell you which internal golden base should be rebuilt.

**How it plugs in:**
Its minimal acquisition fan-out output is the family-level input for the upstream acquisition child workflow.

### 5. Child fan-out: refresh-base-family
The parent fans out one child per family refresh plan.

Each child should eventually:
1. validate that the upstream source is corporate-approved,
2. require a pinned digest unless explicitly overridden by policy,
3. copy the approved upstream base into a handoff location,
4. pass that artifact to the existing cert injection, hardening, rebuild, verification, and publish process.

**Purpose:**
Acquire the approved upstream base for the internal base image family.

**Why it is needed:**
This is the step that actually removes the current manual “go to Red Hat, grab newer base, add certs, push internally” work.

**How it plugs in:**
This is the upstream acquisition unit. One family in, one approved upstream base handoff out.

## Why family-level rebuild is the correct action
A single scanner event on an application image should usually not cause a custom rebuild of that app image.

In this environment, the real controlled remediation unit is typically the internal base family:
- `ubi9-openjdk-17`
- `ubi9-nginx`
- `ubi9-python-311`
- etc.

So the correct reactive flow is:
- scanner finding occurs,
- image is mapped to base family,
- family refresh is planned once,
- internal refreshed base is rebuilt and published once.

That gives you the “only act when needed” behavior without turning the registry into cursed one-off mutations.

## Why metadata-only planning is better
You specifically asked whether this can work off metadata instead of the whole image.

Yes. That is the right move.

### The planner only really needs:
- image identity (image/digest/normalized ref)
- High/Critical counts
- fixable High/Critical counts
- target classes
- managed-base signal and/or base-family hint
- links to evidence reports

That is enough to decide whether to queue a family rebuild.

### It does *not* need:
- a full saved image tarball for every source image
- duplicate scanner runs for everything
- massive storage churn just to make the pipeline feel busy

## Required family catalog
This repo now includes a base-family catalog example:
- `config/base-family-catalog.example.json`

This is the actual source of truth for:
- internal family name
- selectors/matching rules
- approved upstream source image
- customization profile
- target internal registry repo
- publication tag strategy
- verification policy

Without this, the system can detect a problem but cannot deterministically know what to rebuild.

## Current Argo workflow shape
### Parent workflow
- `scotiabank-registry-remediator-orchestrator`

### Child workflows
- `inventory-dedup`
- `plan-refresh-from-scan-metadata`
- `refresh-base-family` (fan-out)

This preserves the parent/child Argo model from the current platform instead of replacing it with some unrelated architecture from outer space.

## Folder layout
- `helm/scotiabank-registry-remediator/`: Helm chart scaffold
- `config/source-locations.example.yaml`: existing scanner input locations
- `config/base-family-catalog.example.json`: managed internal base-family catalog
- `config/ownership-map.example.yaml`: owner/publication defaults around the family catalog
- `scripts/deduplicate_image_records.py`: dedupe runtime image sightings
- `scripts/plan_base_refresh_from_scan_metadata.py`: convert scanner metadata into family refresh plans
- `scripts/refresh_base_family.py`: validate and dry-run approved upstream base acquisition
- `scripts/trivy_to_scan_metadata.py`: convert raw Trivy JSON into the compact `scan-metadata/v1` contract
- `docs/scan-metadata-input-schema.md`: expected compact metadata shape
- `docs/scan-metadata.schema.json`: machine-readable scan metadata contract
- `docs/trivy-reactive-registry-base-refresh.md`: design rationale and end-to-end workflow
- `docs/architecture-flow.md`: Mermaid architecture diagram
- `docs/auth-and-secrets.md`: notes on Dex/LDAP, service accounts, and registry/object-store secrets
- `DEMO.md`: presenter-focused demo script and commands
- `TRACKDOWN.md`: checklist for Rancher, Confluence, and Bitbucket discovery
- `WALKTHROUGH.md`: file-by-file walkthrough of the repo

## New important files
### `scripts/plan_base_refresh_from_scan_metadata.py`
Reads deduplicated runtime image records plus existing scanner metadata plus the base-family catalog and emits:
- per-image evaluations
- deduplicated family refresh plans
- summary counts

### `config/base-family-catalog.example.json`
Defines the mapping between vulnerable runtime images and the managed internal base families to rebuild.
The example catalog includes `ubi9-openjdk-17`, `ubi9-python-311`, and `ubi9-nginx`.
Replace the placeholder digests with corporate-approved pinned digests before execute mode.

### `docs/scan-metadata-input-schema.md`
Defines the compact metadata shape this remediation layer expects from the current scanner pipeline.

### `docs/trivy-reactive-registry-base-refresh.md`
Explains why event-driven-from-Trivy still works, but only if rebuild happens at the family level.

## Scope boundary
### In scope
- consume runtime image inventory from the current stack
- consume existing scanner metadata
- dedupe runtime artifacts
- plan internal base-family refreshes
- scaffold rebuild/rescan/publish of internal base images

### Out of scope for now
- application PR generation
- arbitrary app dependency mutation
- live cluster mutation
- replacing the current scanning/reporting platform

## Will this plug right in?
Short answer: **partially**.

### Already real in this repo
- runtime image dedupe logic
- metadata-driven family refresh planner
- family catalog example
- guarded upstream base acquisition worker for `refresh-base-family`
- updated docs for the existing scanner integration model
- parent/child Argo workflow scaffold around dedupe -> plan -> refresh

### Still scaffold / placeholder
- exact event source integration from the current Aqua/Trivy platform
- upstream Red Hat auth and real digest population in the family catalog
- existing downstream cert/customization/hardening handoff integration
- post-build scan gate wiring
- registry push/signing
- dedupe window / state tracking to suppress duplicate refresh storms

So yes, the architecture is now aligned to the current environment.
No, it is not a finished production implementation yet.

## Example planner input/output flow
### Example inputs
- `examples/unique-images-for-refresh.example.json`
- `examples/scan-metadata.example.json`
- `config/base-family-catalog.example.json`

### Example planner run
```bash
python3 scripts/plan_base_refresh_from_scan_metadata.py \
  examples/unique-images-for-refresh.example.json \
  examples/scan-metadata.example.json \
  config/base-family-catalog.example.json \
  /tmp/refresh-plan-example
```

### Example dedupe run
```bash
python3 scripts/deduplicate_image_records.py \
  examples/collected-image-records.example.json \
  examples/output
```

## Recommended next steps
1. Confirm the exact shape of the current scanner metadata you can export reliably.
2. Map current managed internal bases into `config/base-family-catalog.example.json`.
3. Decide the event handoff mechanism:
   - webhook
   - object-store watcher
   - scheduled Argo wrapper that only reacts to new metadata
4. Replace example upstream digests with approved corporate-pinned Red Hat/internal digests.
5. Wire the upstream handoff directory into the existing cert/hardening/rebuild process.
6. Add candidate verification + publish policy enforcement.
7. Add state recording so repeated scanner events for the same family do not cause rebuild spam.

## If you need the elevator pitch
> The current scanner pipeline keeps doing inventory and vuln detection; this repo consumes its runtime image list and compact vuln metadata, deduplicates affected artifacts, resolves them back to managed internal base families, and rebuilds only the base images that actually need refresh.
