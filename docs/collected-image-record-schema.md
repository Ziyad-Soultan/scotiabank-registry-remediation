# Collected Image Record Schema

This schema defines the **already-collected input records** consumed by the deduplication step.

## Important update
The dedupe script now supports **two input shapes**:

1. **Current nested `images.json` runtime inventory** from the existing cluster image dump agent
2. **Expanded record array** with richer ownership/build metadata

That means you can use the current real-world file immediately instead of having to pre-convert it first.

## Shape 1: Current `images.json` format
This is the format you said exists today:

For this remediation flow, the file should contain all running image references
for the cluster, account, or environment scope being processed. The dedupe and
planner stages only act on images present in this inventory.

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

### How the script treats this format
The script expands each `namespace` + `image` pair into an internal normalized record with fields like:
- `image`
- `sourceType=cluster`
- `sourceName` derived from `project_name`, `epm_code`, or `clusterName`
- `environmentType`
- `clusterName`
- `namespace`
- `ownerTeam` derived from `epm_code`

### Limits of this format
This nested runtime inventory is enough for:
- runtime image dedupe
- cluster / namespace blast-radius mapping
- joining later against scan metadata

But it does **not** carry rich fields like:
- source repo URL
- Dockerfile path
- build pipeline
- owner contact
- PR target info

So for pure registry refresh planning, it is good enough.
For broader remediation ownership workflows, it is still metadata-light.

## Shape 2: Expanded record array
This richer format is still supported when you have more metadata available.

## Purpose
A collected image record represents one sighting of one image from one source.
Sources can be:
- Kubernetes clusters
- registries
- local application-team machine submissions

The dedupe step groups many collected records into one unique artifact while preserving all source/owner metadata.

## Expanded record fields
### Core artifact identity
- `image` or `imageReference` — image reference as seen by the source
- `sourceType` — one of:
  - `cluster`
  - `registry`
  - `local-machine`
- `sourceName` — human-meaningful source identifier
- `environmentType` — one of:
  - `cloud`
  - `on-prem`
  - `local`
  - `shared`
  - `unknown`

### Strongly recommended when available
#### Digest / image metadata
- `digest` — immutable digest if already resolved
- `tag` — tag if known separately from `image`
- `registryName` — registry system name
- `clusterName` — cluster name when source is a cluster
- `machineName` — machine/workstation name when source is local

#### Workload location metadata
- `namespace`
- `workloadKind`
- `workloadName`

#### Ownership metadata
- `ownerTeam`
- `ownerContact`
  - example:
    ```json
    {"slackChannel":"#platform-payments","email":"team@example.com"}
    ```

#### Source-control / PR metadata
- `sourceRepoUrl`
- `sourceRepoPath`
- `dockerfilePath`
- `helmChartPath`
- `buildPipelineUrl`
- `prTargetRepoUrl`
- `prTargetBranch`

#### Extra metadata
- `labels`
- `annotations`
- `submittedAt`
- `notes`

## Expanded JSON shape example

```json
[
  {
    "image": "internal-registry.example.com/platform/python-api:1.2.3",
    "digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "sourceType": "cluster",
    "sourceName": "rancher-prod-a",
    "environmentType": "cloud",
    "clusterName": "rancher-prod-a",
    "registryName": "internal-registry",
    "namespace": "payments",
    "workloadKind": "Deployment",
    "workloadName": "python-api",
    "ownerTeam": "platform-payments",
    "ownerContact": {
      "slackChannel": "#platform-payments",
      "email": "platform-payments@example.com"
    },
    "sourceRepoUrl": "https://github.example.com/scotia/python-api",
    "sourceRepoPath": ".",
    "dockerfilePath": "docker/Dockerfile",
    "helmChartPath": "deploy/chart",
    "buildPipelineUrl": "https://ci.example.com/job/python-api",
    "prTargetRepoUrl": "https://github.example.com/scotia/python-api",
    "prTargetBranch": "main"
  }
]
```

## Normalization rules
- Prefer `digest` when available.
- If both `image` and `imageReference` exist, dedupe logic will prefer `image` first.
- Missing digests are allowed, but then dedupe falls back to Dockerfile-source identity.
- If the input is nested `images.json`, the script expands it automatically before dedupe.
- `sourceRepoUrl` + `dockerfilePath` + normalized image name become much more important when no digest exists.

## Output relationships
One input record becomes:
- one entry inside `sightings.json`, and
- part of one grouped entry inside `unique-images.json`

So if 12 collected records point to the same digest, you get:
- 12 sightings,
- 1 unique image artifact,
- 1 eventual remediation target.
