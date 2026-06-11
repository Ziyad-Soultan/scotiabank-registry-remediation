# Trivy-Reactive Registry Base Refresh Design

## Purpose
Document the recommended architecture for extending the **existing cluster image inventory + Aqua/Trivy reporting pipeline** into a **registry-first internal base image refresh platform**.

## Why this exists
The current system already does the detection part:
- collects running image inventory from clusters
- scans images
- parses vulnerability results
- publishes reports

The missing step is acting on those findings in a controlled way.

The user requirement here is specific:
- stay **event-driven off scanner findings**
- avoid unnecessary upgrades
- focus on **internal registry refresh**, not PRs
- preserve the **parent / child Argo workflow model**
- avoid storing huge image archives when scan metadata already exists

## Core design decision
Use scanner findings as the **trigger**, but rebuild at the **managed internal base-family level**.

Do **not** rebuild one custom fix per flagged application image.

That would create duplicate work, inconsistent lineage, and an absolute clown show in the registry.

## Existing-state assumptions from current docs
The current scanning/reporting stack already provides:
- running image inventory (`images.json`-style output)
- modular Argo workflows with parent/child orchestration
- vulnerability metadata and reports (HTML/JSON/CSV)
- storage handoff via object store and/or PVCs

This redesign intentionally works **with** that architecture instead of replacing it.

## End-to-end flow
### 1. Existing scanner pipeline emits runtime inventory
The current image dump agent produces a running image list for clusters.

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

The dedupe script in this repo now expands that nested format automatically into internal normalized records before grouping unique artifacts.

### 2. Existing scanner pipeline emits vulnerability metadata
Aqua/Trivy scanning continues to produce vulnerability metadata and evidence links.

### 3. Parent remediation workflow starts
The remediation parent workflow is triggered by:
- scanner event/webhook, or
- scheduled wrapper that reacts only to new/changed scanner metadata

### 4. Child: inventory-dedup
Input:
- running image inventory

Output:
- `unique-images.json`
- `sightings.json`
- `dedupe-summary.json`

Purpose:
- collapse repeated runtime sightings into one runtime artifact record while preserving impact locations

### 5. Child: plan-refresh-from-scan-metadata
Inputs:
- `unique-images.json`
- compact scan metadata JSON
- base family catalog

Output:
- `image-evaluations.json`
- `family-refresh-plans.json`
- `family-refresh-summary.json`

Purpose:
- match runtime images to scanner metadata
- determine whether findings are fixable High/Critical base/runtime issues
- resolve the internal base family that owns the problem
- deduplicate many vulnerable app images down to one family refresh plan

### 6. Child fan-out: refresh-base-family
Input:
- one family refresh plan

Action:
- validate the requested upstream vendor image is approved
- require a digest-pinned upstream by default
- copy the approved upstream base into the shared handoff location
- let the existing cert injection, hardening, rebuild, verification, and publish process continue from there

### 7. Optional state/update recording
Store:
- family name
- upstream digest used
- candidate digest produced
- verification summary
- publication decision

This is what prevents duplicate rebuild storms from repeated scanner events.

## Why metadata-only planning is better
### Purpose
Reduce storage and duplicated compute.

### Why it is needed
The scanner stack already knows the important facts. Re-archiving every image again just because another workflow wants to feel involved is wasteful.

### How it plugs in
The planner only needs:
- image identity
- vulnerability counts
- fixable counts
- target classes
- managed-base / family hints
- evidence links

That is enough to decide whether a family refresh should happen.

## Parent / child workflow model
### Parent workflow
Responsibilities:
- sequence the phases
- carry shared handoff paths / artifacts
- fan out family refresh children

### Child workflows
1. `inventory-dedup`
2. `plan-refresh-from-scan-metadata`
3. `refresh-base-family` (fan-out)

This keeps the same Argo mental model the team already understands.

## Family-level dedupe rule
If 30 app images all trace back to `ubi9-openjdk-17`, the system should create:
- **1 family refresh plan**
- not 30 rebuild jobs

That is the entire point of doing this intelligently.

## Required base family catalog
The system needs a catalog mapping internal base families to:
- selectors / matching rules
- approved upstream image source
- customization profile
- target internal registry repository
- publication tags
- verification policy

Without this, the scanner can tell you something is broken, but the rebuild pipeline still has no deterministic idea what to refresh.

## Minimal event-driven decision logic
When scanner metadata indicates a vulnerable running image:
1. does it have High/Critical findings?
2. are any of those findings fixable?
3. does the target class look like a base/runtime issue?
4. is the image part of a managed internal base lineage?
5. can it be mapped to a known base family?

If yes, queue family refresh.

If no, record why and stop.

## Scope boundary
### In scope
- internal UBI/JDK/NGINX/etc. golden base refresh
- Red Hat upstream source resolution
- approved upstream base acquisition
- handoff to existing cert baking / org customization
- downstream candidate build and registry publish integration
- Trivy/Aqua-reactive triggering

### Out of scope for now
- arbitrary application dependency mutation
- per-app one-off image rebuilds
- PR generation
- live cluster mutation

## Recommended safeguards
- family-level dedupe window
- build concurrency limits
- post-build Trivy verification
- immutable candidate tags plus moving approval tags
- state recording of last successful refresh per family

## Straight answer
Yes, the reactive approach can still be done.

The correct way is:
- react to scanner findings,
- use scanner metadata instead of full image archives where possible,
- resolve impacted images back to managed internal base families,
- rebuild/publish those families through parent/child Argo workflows.

That preserves the current operating model while removing the manual “go to Red Hat, grab newer base, add certs, push internally” nonsense.
