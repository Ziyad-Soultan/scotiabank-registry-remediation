# Scan Metadata Input Schema

## Purpose
Define the **compact scanner metadata** this remediation platform expects from the existing Aqua/Trivy reporting stack.

Machine-readable schema:
- `docs/scan-metadata.schema.json`

## Why this exists
The current scanner/reporting stack already produces the important signal:
- which running image was scanned
- whether it has High/Critical findings
- whether those findings are fixable
- whether the finding looks like a base/runtime issue
- where the supporting report lives

That means the remediation platform should consume this metadata directly instead of storing full image archives again.

## How it plugs into the system
1. Existing image dump / scanner pipeline emits `images.json` and scan metadata JSON.
2. `inventory-dedup` turns `images.json` into unique runtime artifacts.
3. `plan-refresh-from-scan-metadata` joins those artifacts with this metadata schema.
4. The planner emits deduplicated **base-family refresh plans** for upstream acquisition and downstream rebuild processing.

## Expected top-level shape
A JSON array of scan metadata records:

```json
[
  {
    "schemaVersion": "scan-metadata/v1",
    "image": "registry.corp/apps/payments-api:1.2.3",
    "digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "scanner": "trivy",
    "scannerVersion": "0.52.2",
    "scanTimestamp": "2026-06-11T14:30:00Z",
    "baseFamily": "ubi9-openjdk-17",
    "baseImage": {
      "image": "registry.corp/base/ubi9-openjdk-17:approved",
      "digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "family": "ubi9-openjdk-17",
      "source": "scanner-lineage"
    },
    "managedBaseImage": true,
    "targetClasses": ["rhel-base", "jdk-runtime"],
    "criticalCount": 1,
    "highCount": 4,
    "fixableCriticalCount": 1,
    "fixableHighCount": 3,
    "summaryPath": "gs://scanner/metadata/payments-api-summary.json",
    "reportPath": "gs://scanner/reports/payments-api.html"
  }
]
```

## Fields
### Identity and lookup
- `schemaVersion`: currently `scan-metadata/v1`
- `image`: original image reference scanned
- `digest`: immutable digest if known
- `normalizedReference`: optional normalized image ref
- `normalizedImageName`: optional normalized repo/name
- `canonicalKey`: optional precomputed dedupe key

At least one of `digest`, `image`, `normalizedReference`, or `normalizedImageName` should be present so the planner can match metadata to runtime artifacts.

### Scanner provenance
- `scanner`: `aqua`, `trivy`, or org-specific label
- `scannerVersion`: scanner version when available
- `scanTimestamp`: UTC ISO-8601 timestamp for when the scan happened
- `scanRunId`: optional workflow/run identifier
- `summaryPath`: path/URL to compact machine-readable evidence
- `reportPath`: path/URL to HTML/JSON human-readable report
- `rawReportPath`: optional path to raw Trivy/Aqua JSON for audit/debug

### Vulnerability summary
- `criticalCount`
- `highCount`
- `fixableCriticalCount`
- `fixableHighCount`

You may also nest these under:

```json
"summary": {
  "criticalCount": 1,
  "highCount": 4,
  "fixableCriticalCount": 1,
  "fixableHighCount": 3
}
```

The planner supports either form.

### Routing / classification
- `baseFamily`: optional explicit internal family name, e.g. `ubi9-openjdk-17`
- `baseImage`: optional base-image lineage object containing `image`, `digest`, `family`, and `source`
- `managedBaseImage`: boolean indicating whether the impacted image belongs to a managed internal base lineage
- `targetClasses`: array such as:
  - `rhel-base`
  - `os-package`
  - `nginx`
  - `java-runtime`
  - `jdk-runtime`
  - `python-runtime`
  - `python`
  - `java`

## Minimum useful record
For the planner to make a decision, the metadata should ideally include:
- image or digest
- scan timestamp
- critical/high summary
- fixable summary
- target classes
- managed-base signal and/or base-family hint

## Can Trivy generate this?
Yes. A Trivy container can emit raw JSON:

```bash
trivy image \
  --format json \
  --output /work/shared/raw-trivy/payments-api.json \
  registry.corp/apps/payments-api:1.2.3
```

Then a small adapter step can convert raw Trivy JSON into this compact contract:

```bash
python3 scripts/trivy_to_scan_metadata.py \
  /work/shared/raw-trivy/payments-api.json \
  /work/shared/scan-metadata/payments-api.scan-metadata.json \
  --image registry.corp/apps/payments-api:1.2.3 \
  --digest sha256:1111111111111111111111111111111111111111111111111111111111111111 \
  --base-family ubi9-openjdk-17 \
  --base-image registry.corp/base/ubi9-openjdk-17:approved \
  --base-digest sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --managed-base-image \
  --scanner-version 0.52.2 \
  --raw-report-path /work/shared/raw-trivy/payments-api.json \
  --report-path /work/shared/reports/payments-api.html \
  --summary-path /work/shared/scan-metadata/payments-api.scan-metadata.json
```

The scanner workflow should provide lineage fields such as `baseFamily`,
`baseImage`, and `managedBaseImage` from image labels, scanner enrichment, or an
internal inventory/catalog lookup. Trivy alone can count vulnerabilities, but it
does not magically know the bank's managed base family policy.

## What should trigger automatic family refresh planning
The scaffold currently expects all of these to be true:
1. High or Critical findings exist
2. at least one High or Critical finding is fixable
3. target class looks like a base/runtime issue
4. the image is part of a managed internal base lineage
5. a base family can be resolved from metadata or catalog rules

## What should *not* trigger automatic family refresh planning
- app dependency-only findings (`python`, `java`) with no base/runtime evidence
- images not marked as managed base lineage
- findings with no fixable High/Critical counts
- findings that cannot be mapped to an internal base family

## Storage recommendation
Prefer keeping:
- `images.json`
- compact scan metadata JSON
- optional HTML/CSV evidence links

Avoid keeping large duplicate image archives in this remediation pipeline unless you are forced to debug a specific case.

That storage bill gets stupid fast for no benefit.
