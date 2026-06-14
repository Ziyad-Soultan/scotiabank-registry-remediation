# Argo HK Dev Bring-Up Guide

This document is the practical setup guide for getting the remediation scaffold working in the real dev environment inside the `argo-hk` namespace.

If you are new to the repo, good news: the skeleton already exists.
If you thought that meant "install chart, win prize, go home," unfortunately no. You still need to wire the environment-specific pieces so the workflow can actually run.

## 1. What already exists in the repo

The Helm/Argo scaffold already defines the core workflow chain.

Main chart path:
- `helm/scotiabank-registry-remediator/`

Exact workflow/control-plane files:
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-orchestrator.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-collect-cluster-images.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-inventory-dedup.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-scan-unique-images.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-scan-metadata-planner.yaml`
- `helm/scotiabank-registry-remediator/templates/workflowtemplate-remediate-image.yaml`
- `helm/scotiabank-registry-remediator/templates/configmap-metadata.yaml`
- `helm/scotiabank-registry-remediator/templates/cronworkflow-scheduled.yaml`
- `helm/scotiabank-registry-remediator/templates/pvc-shared-data.yaml`
- `helm/scotiabank-registry-remediator/values.yaml`
- `helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml`

Mounted helper/config payloads:
- `helm/scotiabank-registry-remediator/files/collect_cluster_images.py`
- `helm/scotiabank-registry-remediator/files/deduplicate_image_records.py`
- `helm/scotiabank-registry-remediator/files/scan_unique_images.py`
- `helm/scotiabank-registry-remediator/files/trivy_to_scan_metadata.py`
- `helm/scotiabank-registry-remediator/files/plan_base_refresh_from_scan_metadata.py`
- `helm/scotiabank-registry-remediator/files/refresh_base_family.py`
- `helm/scotiabank-registry-remediator/files/rebuild_family_candidate.py`
- `helm/scotiabank-registry-remediator/files/prod-clusters.example.json`
- `helm/scotiabank-registry-remediator/files/base-family-catalog.example.json`
- `helm/scotiabank-registry-remediator/files/source-locations.example.yaml`
- `helm/scotiabank-registry-remediator/files/ownership-map.example.yaml`

## 2. What the workflow actually does

The top-level orchestrator runs these phases in order:

1. `collect-cluster-images`
2. `inventory-dedup`
3. `scan-unique-images`
4. `plan-family-refreshes`
5. `refresh-each-family`

That means the dev objective is not just "deploy YAMLs." The real objective is proving that each phase can execute in `argo-hk` with:
- real namespace access
- real worker images
- real config
- safe dry-run behavior

## 3. Files you must care about

### Helm templates that define Kubernetes/Argo resources

These are the files that belong in `helm/.../templates/` because they render real cluster resources:

Already present:
- `templates/workflowtemplate-orchestrator.yaml`
- `templates/workflowtemplate-collect-cluster-images.yaml`
- `templates/workflowtemplate-inventory-dedup.yaml`
- `templates/workflowtemplate-scan-unique-images.yaml`
- `templates/workflowtemplate-scan-metadata-planner.yaml`
- `templates/workflowtemplate-remediate-image.yaml`
- `templates/configmap-metadata.yaml`
- `templates/cronworkflow-scheduled.yaml`
- `templates/pvc-shared-data.yaml`

Still missing and likely needed:
- `templates/serviceaccount.yaml`
- `templates/role.yaml`
- `templates/rolebinding.yaml`
- optionally `templates/clusterrole.yaml`
- optionally `templates/clusterrolebinding.yaml`
- optionally `templates/secret-registry-auth.yaml`
- optionally `templates/networkpolicy.yaml`

Rule of thumb:
- if it creates a Kubernetes object, it belongs in `templates/`
- if it is just environment-specific values, it belongs in a values file
- if it is mounted script/config content, it belongs in `files/`

### Values files

Base chart defaults:
- `helm/scotiabank-registry-remediator/values.yaml`

Namespace/environment-specific override:
- `helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml`

Do not cram all dev config into the base file unless you enjoy making future you hate present you.

### Mounted config/script files

Used by ConfigMaps and runtime helpers:
- `helm/scotiabank-registry-remediator/files/*.py`
- `helm/scotiabank-registry-remediator/files/*.json`
- `helm/scotiabank-registry-remediator/files/*.yaml`

## 4. What is missing right now

The chart is not fully environment-wired yet. These are the real gaps:

1. No explicit ServiceAccount / Role / RoleBinding templates in the chart
2. `workflowUtils` default image is `python:3.12-slim`, which does not contain `kubectl`
3. `scannerWorker`, `builder`, and `rebuildWorker` image references are placeholders
4. cluster config is still example content
5. family catalog is still example content
6. secret/auth strategy for registries is not fully wired in the chart
7. refresh/rebuild/publish parts are intentionally incomplete and should stay dev-safe at first

So yes, this is a scaffold. Useful scaffold, but scaffold nonetheless.

## 5. Namespace and runtime target

For this dev bring-up, the namespace is:
- `argo-hk`

That namespace should be used consistently in:
- Helm release commands
- values override files
- Argo submit commands
- resource verification commands

## 6. Prerequisites you need before touching Helm too hard

Before first deployment, confirm all of this:

### Namespace / Argo prerequisites
- You can access `argo-hk`
- Argo Workflows CRDs are installed
- You can create/read WorkflowTemplates and CronWorkflows in `argo-hk`
- You can submit workflows in `argo-hk`

### RBAC prerequisites
You need a service account strategy.

Choose one:
1. Bank/platform-managed SA already exists in `argo-hk`
2. This chart creates its own SA and bindings

At minimum, the workflow identity must be able to:
- read ConfigMaps
- mount/use PVC-backed storage
- read pods across namespaces if inventory collection uses in-cluster cluster-wide reads
- potentially read namespaces

### Worker image prerequisites
You need real images for these roles:

1. workflow utils image
   - must contain `python3`
   - must contain `kubectl`

2. scanner worker image
   - must contain `python3`
   - must contain `trivy`

3. builder image
   - must contain `python3`
   - must contain `skopeo`

4. rebuild worker image
   - should contain `python3`
   - can remain placeholder-safe initially

### Registry/auth prerequisites
You need to know how the workflow will authenticate to:
- internal registry pulls/pushes
- `registry.redhat.io` if upstream acquisition touches it in any meaningful execute path

For first dev run, keep refresh in `dry-run` and rebuild in `placeholder` mode.
That reduces the blast radius while still proving orchestration.

## 7. The dev values file to use

The repo includes:
- `helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml`

That file should hold all namespace-specific settings for `argo-hk`, including:
- namespace
- service account name
- PVC name / storage class / size
- worker image refs
- cron schedule
- candidate registry
- safe dev execution modes

You should update placeholders in that file with real values before first deploy.

## 8. Cluster config you need to set up

Used by:
- `files/collect_cluster_images.py`
- `templates/workflowtemplate-collect-cluster-images.yaml`

Files to update:
- `config/prod-clusters.example.json`
- `helm/scotiabank-registry-remediator/files/prod-clusters.example.json`

For first bring-up, do not model 50 clusters because you hate yourself.
Use the single real dev target you can access.

Expected shape:

```json
{
  "clusters": [
    {
      "clusterName": "argo-hk-dev",
      "kubectlContext": "REPLACE_WITH_REAL_CONTEXT",
      "epm_code": "gpedev",
      "project_name": "shared-platform",
      "environmentType": "dev"
    }
  ]
}
```

Important note:
`collect_cluster_images.py` currently shells out to:
- `kubectl --context <context> get pods --all-namespaces -o json`

That means you must decide how auth works:

Option A: in-cluster auth
- preferred for real cluster deployment
- may require adjusting collector behavior if context switching is unnecessary or unavailable

Option B: mount kubeconfig with named contexts
- workable in dev
- uglier operationally

For the first test, keep it as simple as possible.

## 9. Family catalog you need to set up

Used by:
- `files/scan_unique_images.py`
- `files/plan_base_refresh_from_scan_metadata.py`
- `files/refresh_base_family.py`

Files to update:
- `config/base-family-catalog.example.json`
- `helm/scotiabank-registry-remediator/files/base-family-catalog.example.json`

For first validation, keep the catalog tiny:
- 1 UBI/RHEL family
- 1 Python or JDK family

Each family entry should include:
- selectors
- approved upstream image
- pinned digest
- target repository
- policy thresholds

Do not pretend example digests are fine. They are not. They are decorative lies until replaced.

## 10. RBAC templates you probably need to add

These do not currently exist in the chart and should be added if the namespace does not already provide them:

- `helm/scotiabank-registry-remediator/templates/serviceaccount.yaml`
- `helm/scotiabank-registry-remediator/templates/role.yaml`
- `helm/scotiabank-registry-remediator/templates/rolebinding.yaml`

Maybe also:
- `helm/scotiabank-registry-remediator/templates/clusterrole.yaml`
- `helm/scotiabank-registry-remediator/templates/clusterrolebinding.yaml`

Likely permissions to think through:
- get/list/watch `configmaps`
- get/list/watch `pods`
- get/list/watch `namespaces`
- Argo workflow-related reads if needed by platform policy

If the collector is reading pods across all namespaces, namespace-local Role permissions may not be enough.
That is the kind of detail that blows up a demo if you ignore it.

## 11. Step-by-step bring-up process

### Step 1: Update the dev values file

File:
- `helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml`

Fill in:
- real storage class
- real artifact repository path
- real service account name
- real worker image refs
- real candidate registry

### Step 2: Update cluster config

Files:
- `config/prod-clusters.example.json`
- `helm/scotiabank-registry-remediator/files/prod-clusters.example.json`

Set the actual dev cluster target and auth model.

### Step 3: Update family catalog

Files:
- `config/base-family-catalog.example.json`
- `helm/scotiabank-registry-remediator/files/base-family-catalog.example.json`

Start with 1-2 families only.

### Step 4: Add ServiceAccount/RBAC templates if needed

Files to create:
- `templates/serviceaccount.yaml`
- `templates/role.yaml`
- `templates/rolebinding.yaml`
- maybe cluster-scoped variants if inventory read requires them

### Step 5: Render the chart locally

From repo root:

```bash
helm template scotia-remediator-dev helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

You want to confirm:
- namespace is `argo-hk`
- all templates render
- ConfigMaps include your updated files
- PVC is present
- no obvious unresolved placeholders remain for required fields

### Step 6: Lint the chart

```bash
helm lint helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

### Step 7: Install into `argo-hk`

```bash
helm upgrade --install scotia-remediator-dev helm/scotiabank-registry-remediator -n argo-hk -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

### Step 8: Verify resources

```bash
kubectl get workflowtemplates,cronworkflows,configmaps,pvc,sa -n argo-hk
```

Success means:
- WorkflowTemplates exist
- ConfigMaps exist
- PVC exists and is `Bound`
- SA exists if expected

### Step 9: Submit the orchestrator manually

Do not start with cron like a maniac.
Run manually first.

```bash
argo submit --from workflowtemplate/scotiabank-registry-remediator-orchestrator -n argo-hk
```

If no `argo` CLI is available, use the Argo UI.

### Step 10: Watch the workflow

```bash
argo list -n argo-hk
argo get <workflow-name> -n argo-hk
argo logs <workflow-name> -n argo-hk
```

### Step 11: Validate each stage

#### collect-cluster-images
Expect:
- `*.images.json` written
- no kubectl auth/permission failure

#### inventory-dedup
Expect:
- `unique-images.json`
- `unique-images.min.json`
- `sightings.json`
- `dedupe-summary.json`

#### scan-unique-images
Expect:
- `scan-metadata.json`
- raw reports under trivy output dir
- no missing `trivy` binary

#### plan-family-refreshes
Expect:
- `family-refresh-plans.json`
- `family-acquisition-fanout.min.json`
- sensible family matches

#### refresh-each-family
Expect:
- dry-run upstream validation output
- placeholder rebuild handoff output
- no registry mutation if modes are still safe

### Step 12: Inspect shared output paths

Configured paths:
- `/work/shared/cluster-images`
- `/work/shared/dedupe-output`
- `/work/shared/trivy-raw`
- `/work/shared/refresh-plan`
- `/work/shared/upstream-bases`
- `/work/shared/rebuild-output`

That PVC is your evidence locker. Use it.

### Step 13: Only enable CronWorkflow after manual success

The file is:
- `helm/scotiabank-registry-remediator/templates/cronworkflow-scheduled.yaml`

The schedule is controlled by:
- `schedule.cron` in `values-argo-hk-dev.yaml`

Recommended first dev schedule:
- every 6 hours, not some unhinged rapid-fire schedule that just creates repeated failure spam

## 12. Suggested first milestone

Do not define success as full autonomous remediation.
That is how you accidentally sign yourself up for a month of nonsense.

Define first success as:

"The chart deploys to `argo-hk` and a manual run completes inventory -> dedupe -> scan -> plan -> refresh dry-run handoff for a real dev cluster target and 1-2 base families."

That is real progress.
That is demoable.
That is sane.

## 13. Common failure modes

1. `kubectl` missing in workflow utils image
2. `trivy` missing in scanner worker image
3. `skopeo` missing in builder image
4. service account lacks pod read permissions
5. PVC is Pending because storage class is wrong
6. family catalog selectors do not match actual images
7. example digests were never replaced
8. CronWorkflow started before manual runs were ever validated

## 14. Quick command reference

Render:

```bash
helm template scotia-remediator-dev helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

Lint:

```bash
helm lint helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

Install:

```bash
helm upgrade --install scotia-remediator-dev helm/scotiabank-registry-remediator -n argo-hk -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

Verify resources:

```bash
kubectl get workflowtemplates,cronworkflows,configmaps,pvc,sa -n argo-hk
```

Submit workflow:

```bash
argo submit --from workflowtemplate/scotiabank-registry-remediator-orchestrator -n argo-hk
```

Watch workflow:

```bash
argo list -n argo-hk
argo get <workflow-name> -n argo-hk
argo logs <workflow-name> -n argo-hk
```

## 15. Bottom line

Yes, the YAML resources belong in `helm/.../templates`.
But the full bring-up is really three buckets:

1. `templates/`
   - Kubernetes/Argo resources
2. `values-argo-hk-dev.yaml`
   - namespace-specific wiring for `argo-hk`
3. `files/`
   - mounted scripts and mounted runtime config payloads

That is the clean layout.
That is how you keep this from turning into a cursed pile of one-off edits.
