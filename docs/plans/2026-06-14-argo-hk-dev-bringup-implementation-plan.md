# Argo HK Dev Bring-Up Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Wire the `scotiabank-registry-remediator` Helm/Argo scaffold into the `argo-hk` dev namespace so the team can run a real end-to-end dev workflow: collect cluster images -> dedupe -> scan unique images -> plan base-family refreshes -> execute refresh dry-run handoff.

**Architecture:** Keep Helm as the packaging layer and Argo Workflows as the execution layer. Use a namespace-specific values override for `argo-hk`, keep risky stages in `dry-run` / `placeholder` mode, and add the missing environment integration pieces explicitly instead of pretending the scaffold is already production-ready.

**Tech Stack:** Helm v3/v4, Kubernetes, Argo Workflows, Python helper scripts mounted via ConfigMaps, Trivy, kubectl, skopeo, PVC-backed shared workflow storage.

---

## Working assumptions

1. The target Argo namespace is `argo-hk`.
2. The chart path is `helm/scotiabank-registry-remediator/`.
3. The orchestrator entrypoint is `templates/workflowtemplate-orchestrator.yaml`.
4. First success criteria are dev-safe and non-mutating:
   - chart renders cleanly
   - chart installs into `argo-hk`
   - orchestrator can be submitted manually
   - inventory, dedupe, scan, and planning phases run successfully
   - refresh step stays in `dry-run`
5. Publishing rebuilt images, rescan gates, cooldown/state tracking, and notifications remain follow-up work.

---

## Task 1: Create the namespace-specific Helm values file

**Objective:** Add a real dev override file for `argo-hk` so namespace-specific config is not jammed into the base `values.yaml`.

**Files:**
- Create: `helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml`
- Reference: `helm/scotiabank-registry-remediator/values.yaml`

**Step 1: Create the override file**

Populate the file with the namespace, service account, PVC, schedule, worker image placeholders, and safe execution modes.

Use this as the starting content:

```yaml
namespace: "argo-hk"

serviceAccount:
  create: false
  name: "scotiabank-registry-remediator"

argo:
  workflowLabels:
    app.kubernetes.io/part-of: scotiabank-registry-remediator
    environment: dev
    platform.bank/environment: dev
    platform.bank/namespace: argo-hk
  artifactRepository:
    bucketOrPath: "REPLACE_WITH_ARGO_ARTIFACT_REPOSITORY"
  pvc:
    enabled: true
    claimName: "scotiabank-registry-remediator-shared"
    mountPath: /work/shared
    storageClassName: "REPLACE_WITH_ARGO_HK_STORAGE_CLASS"
    size: 20Gi

schedule:
  cron: "0 */6 * * *"

images:
  workflowUtils:
    repository: "REPLACE_WITH_APPROVED_UTILS_IMAGE"
    tag: "dev"
  trivy:
    repository: aquasec/trivy
    tag: "0.52.2"
  scannerWorker:
    repository: "REPLACE_WITH_APPROVED_TRIVY_PYTHON_IMAGE"
    tag: "dev"
  builder:
    repository: "REPLACE_WITH_APPROVED_SKOPEO_IMAGE"
    tag: "dev"
  rebuildWorker:
    repository: "REPLACE_WITH_APPROVED_REBUILD_IMAGE"
    tag: "dev"

inventory:
  clusterImageInventoryPath: "/work/shared/cluster-images"
  fileGlob: "*.images.json"
  expectsPerClusterFiles: true
  collection:
    clusterConfigPath: "/opt/remediator/cluster-config/prod-clusters.example.json"
    kubectlBinary: "kubectl"
    timeoutSeconds: 180

scanner:
  metadataOutputPath: "/work/shared/scan-metadata.json"
  rawReportDir: "/work/shared/trivy-raw"
  mode: dry-run
  timeoutSeconds: 1800

familyCatalog:
  inputPath: "/opt/remediator/catalog/base-family-catalog.example.json"
  configMapName: scotiabank-registry-remediator-family-catalog

workflowPaths:
  dedupeOutputDir: "/work/shared/dedupe-output"
  refreshPlanOutputDir: "/work/shared/refresh-plan"
  upstreamBaseHandoffDir: "/work/shared/upstream-bases"
  rebuildOutputDir: "/work/shared/rebuild-output"

publication:
  candidateRegistry: "REPLACE_WITH_DEV_CANDIDATE_REGISTRY"

refreshBaseFamily:
  mode: dry-run
  allowedUpstreamSourceTypes:
    - redhat-catalog
    - internal-approved-registry
  allowedUpstreamRegistries:
    - registry.redhat.io
  allowUnpinnedApprovedUpstream: false

rebuild:
  mode: placeholder
  workRepoPath: "/work/rebuild-placeholder"
```

**Step 2: Render the chart with the new override**

Run:

```bash
helm template scotia-remediator-dev helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

Expected:
- namespace should render as `argo-hk`
- all WorkflowTemplates, ConfigMaps, PVC, and CronWorkflow should render
- placeholder strings should still be visible only where real infra inputs are still missing

**Step 3: Commit**

```bash
git add helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
git commit -m "feat: add argo-hk dev values override"
```

---

## Task 2: Add a detailed dev bring-up runbook

**Objective:** Create one doc that tells an engineer exactly what to set up in `argo-hk`, what files matter, what commands to run, and what success looks like.

**Files:**
- Create: `docs/argo-hk-dev-bringup.md`
- Reference: `helm/scotiabank-registry-remediator/templates/*.yaml`
- Reference: `helm/scotiabank-registry-remediator/files/*.py`

**Step 1: Document the exact files that define the control plane**

The runbook must explicitly call out:

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

**Step 2: Document the missing infra pieces that are not yet templated**

Call out these to-be-added templates explicitly:

- `helm/scotiabank-registry-remediator/templates/serviceaccount.yaml`
- `helm/scotiabank-registry-remediator/templates/role.yaml`
- `helm/scotiabank-registry-remediator/templates/rolebinding.yaml`
- optional: `helm/scotiabank-registry-remediator/templates/secret-registry-auth.yaml`
- optional: `helm/scotiabank-registry-remediator/templates/networkpolicy.yaml`

Also state what each one is for.

**Step 3: Document the dev bring-up sequence**

Runbook should cover:
1. verify namespace + Argo access
2. verify service account / RBAC
3. build or obtain approved worker images
4. replace example cluster config and family catalog content
5. render chart
6. install chart into `argo-hk`
7. manually submit orchestrator
8. inspect PVC/artifacts for outputs
9. debug per-stage failures
10. enable cron only after manual runs are green

**Step 4: Commit**

```bash
git add docs/argo-hk-dev-bringup.md
git commit -m "docs: add argo-hk dev bring-up guide"
```

---

## Task 3: Add and version the implementation plan

**Objective:** Save this plan in-repo so future implementation is not trapped inside chat history.

**Files:**
- Create: `docs/plans/2026-06-14-argo-hk-dev-bringup-implementation-plan.md`

**Step 1: Save the implementation plan**

Include:
- exact files to touch
- exact Helm commands
- exact Argo commands
- required secrets/images/RBAC decisions
- verification checkpoints after each milestone

**Step 2: Verify the file is committed**

Run:

```bash
git status --short docs/plans/2026-06-14-argo-hk-dev-bringup-implementation-plan.md
```

Expected:
- file should appear as added or tracked-modified before commit

**Step 3: Commit**

```bash
git add docs/plans/2026-06-14-argo-hk-dev-bringup-implementation-plan.md
git commit -m "docs: add argo-hk implementation plan"
```

---

## Task 4: Verify Helm chart behavior before cluster deployment

**Objective:** Make sure the repo can at least render and package before wasting time in the cluster.

**Files:**
- Verify: `helm/scotiabank-registry-remediator/Chart.yaml`
- Verify: `helm/scotiabank-registry-remediator/templates/*.yaml`
- Verify: `helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml`

**Step 1: Render the chart**

Run:

```bash
helm template scotia-remediator-dev helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml > /tmp/scotia-remediator-dev-rendered.yaml
```

Expected:
- exit code 0
- rendered YAML exists
- namespace is `argo-hk`

**Step 2: Lint the chart**

Run:

```bash
helm lint helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

Expected:
- no template syntax failures
- any warnings should be understandable and documented

**Step 3: Review critical rendered references**

Check for:
- `namespace: "argo-hk"`
- service account name matches expected account
- PVC claim name matches expected shared storage claim
- no missing config map names
- no obvious placeholder values accidentally left in a field required for first install

**Step 4: Commit any required follow-up fixes**

```bash
git add helm/scotiabank-registry-remediator
git commit -m "fix: correct argo-hk render-time config"
```

---

## Task 5: Prepare cluster configuration for the dev environment

**Objective:** Replace toy example content with a real dev-cluster-safe configuration.

**Files:**
- Modify: `config/prod-clusters.example.json`
- Modify: `helm/scotiabank-registry-remediator/files/prod-clusters.example.json`
- Modify: `config/base-family-catalog.example.json`
- Modify: `helm/scotiabank-registry-remediator/files/base-family-catalog.example.json`

**Step 1: Trim the cluster config to the actual dev target**

For first bring-up, use only the real dev cluster/context you have access to.

Expected fields:

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

**Step 2: Shrink the family catalog to 1-2 families for first validation**

Start with a tiny set such as:
- one UBI/RHEL family
- one Python or JDK family

Each entry must include:
- selectors
- approved upstream image
- pinned digest
- publication target repository
- policy thresholds

**Step 3: Keep refresh in dry-run**

Do not enable any push/publish behavior until:
- selector matching is proven
- upstream validation is proven
- registry auth is wired

**Step 4: Commit**

```bash
git add config/prod-clusters.example.json config/base-family-catalog.example.json helm/scotiabank-registry-remediator/files/prod-clusters.example.json helm/scotiabank-registry-remediator/files/base-family-catalog.example.json
git commit -m "feat: add dev-safe cluster and family catalog config"
```

---

## Task 6: Add missing workload identity and RBAC templates

**Objective:** Stop relying on magic. Add the missing Kubernetes identity objects or explicitly document the pre-created bank-managed ones.

**Files:**
- Create: `helm/scotiabank-registry-remediator/templates/serviceaccount.yaml`
- Create: `helm/scotiabank-registry-remediator/templates/role.yaml`
- Create: `helm/scotiabank-registry-remediator/templates/rolebinding.yaml`
- Optional create: `helm/scotiabank-registry-remediator/templates/clusterrole.yaml`
- Optional create: `helm/scotiabank-registry-remediator/templates/clusterrolebinding.yaml`

**Step 1: Decide whether the service account is chart-managed or platform-managed**

Use one of these modes:
- bank-managed SA already exists in `argo-hk` -> keep `serviceAccount.create: false`
- chart manages SA -> set `serviceAccount.create: true` and render the account in-template

**Step 2: Add minimum namespace permissions**

The Role should normally allow:
- get/list/watch configmaps
- get/list/watch persistentvolumeclaims (if needed by policy)
- get/list/watch workflows/workflowtemplates/cronworkflows in the Argo API groups if runtime reads require it

**Step 3: Evaluate whether collector needs cluster-wide read**

`collect_cluster_images.py` calls `kubectl get pods --all-namespaces`.

That means first dev bring-up must answer this ugly but important question:
- will the workflow read only the current cluster using in-cluster auth?
- or will it mount a kubeconfig and jump contexts?

If it needs cross-namespace pod read in-cluster, you likely need ClusterRole rules for:
- get/list/watch pods
- get/list/watch namespaces

**Step 4: Render and review RBAC objects**

Run:

```bash
helm template scotia-remediator-dev helm/scotiabank-registry-remediator -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml | less
```

Expected:
- service account, role, and bindings render into `argo-hk`
- names match the values override

**Step 5: Commit**

```bash
git add helm/scotiabank-registry-remediator/templates/serviceaccount.yaml helm/scotiabank-registry-remediator/templates/role.yaml helm/scotiabank-registry-remediator/templates/rolebinding.yaml
git commit -m "feat: add argo-hk service account and RBAC templates"
```

---

## Task 7: Build or source the required worker images

**Objective:** Make the workflow containers actually capable of doing what the scripts ask them to do.

**Files:**
- No repo file required if images already exist
- Otherwise create build context/docs outside the chart and update `values-argo-hk-dev.yaml`

**Step 1: Provide a real workflow utils image**

Must include:
- python3
- kubectl

Reason:
- `files/collect_cluster_images.py` shells out to `kubectl`

**Step 2: Provide a real scanner worker image**

Must include:
- python3
- trivy

Reason:
- `files/scan_unique_images.py` shells out to `trivy image`

**Step 3: Provide a real builder image**

Must include:
- python3
- skopeo

Reason:
- `files/refresh_base_family.py` performs approved upstream acquisition

**Step 4: Provide a placeholder-safe rebuild image**

Must include at minimum:
- python3

Reason:
- `files/rebuild_family_candidate.py` is still placeholder mode but must still execute

**Step 5: Record final image refs in `values-argo-hk-dev.yaml`**

Run:

```bash
git add helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
git commit -m "chore: wire approved worker images for argo-hk dev"
```

---

## Task 8: Install into `argo-hk` and run the first manual workflow

**Objective:** Prove the dev control plane works in the real environment before enabling cron.

**Files:**
- Deploy: rendered resources from `helm/scotiabank-registry-remediator/`

**Step 1: Install or upgrade the chart**

Run:

```bash
helm upgrade --install scotia-remediator-dev helm/scotiabank-registry-remediator -n argo-hk -f helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
```

Expected:
- release installs successfully
- WorkflowTemplates exist in `argo-hk`
- ConfigMaps exist in `argo-hk`
- PVC binds successfully

**Step 2: Verify resources**

Run:

```bash
kubectl get workflowtemplates,cronworkflows,configmaps,pvc,sa -n argo-hk
```

Expected:
- orchestrator and child templates listed
- PVC status is `Bound`
- service account exists if chart-managed or platform-managed

**Step 3: Submit manually**

Run:

```bash
argo submit --from workflowtemplate/scotiabank-registry-remediator-orchestrator -n argo-hk
```

If Argo CLI is unavailable, submit from the Argo UI.

**Step 4: Watch the run**

Run:

```bash
argo list -n argo-hk
argo get <workflow-name> -n argo-hk
argo logs <workflow-name> -n argo-hk
```

Expected per stage:
- collector writes `*.images.json`
- dedupe writes `unique-images.json`, `sightings.json`, `dedupe-summary.json`
- scan writes `scan-metadata.json` and raw Trivy reports
- planner writes `family-refresh-plans.json` and `family-acquisition-fanout.min.json`
- refresh writes dry-run upstream acquisition + rebuild handoff output

**Step 5: Commit any fixes from first-run debugging**

```bash
git add .
git commit -m "fix: resolve argo-hk first-run issues"
```

---

## Task 9: Verify outputs and define the go/no-go gate for cron

**Objective:** Decide when the pipeline is healthy enough for scheduled execution.

**Files:**
- Inspect output paths configured in `values-argo-hk-dev.yaml`

**Step 1: Inspect shared workflow outputs**

Expected paths:
- `/work/shared/cluster-images`
- `/work/shared/dedupe-output`
- `/work/shared/trivy-raw`
- `/work/shared/refresh-plan`
- `/work/shared/upstream-bases`
- `/work/shared/rebuild-output`

**Step 2: Define the minimum green criteria**

Cron must remain disabled or unused until all are true:
- manual orchestrator run succeeds
- family matching is correct for known sample images
- refresh worker validates approved upstream refs correctly
- dry-run outputs are understandable and auditable
- no permission errors remain

**Step 3: Only then enable recurring execution**

Use:
- `templates/cronworkflow-scheduled.yaml`
- `schedule.cron` in `values-argo-hk-dev.yaml`

Suggested first schedule:
- every 6 hours, not every 5 minutes like an over-caffeinated maniac

**Step 4: Commit**

```bash
git add helm/scotiabank-registry-remediator/values-argo-hk-dev.yaml
git commit -m "chore: enable argo-hk dev schedule after green manual run"
```

---

## Verification checklist

- [ ] `values-argo-hk-dev.yaml` exists and pins namespace to `argo-hk`
- [ ] runbook exists with exact file paths and commands
- [ ] implementation plan is saved in `docs/plans/`
- [ ] chart renders with the `argo-hk` override
- [ ] service account / RBAC strategy is explicit
- [ ] worker image requirements are explicit
- [ ] cluster config is narrowed to the real dev cluster
- [ ] family catalog is narrowed to 1-2 test families
- [ ] first manual workflow run is successful in `dry-run`
- [ ] cron remains secondary until manual runs are green

## Notes for the actual implementer

1. The current scaffold is useful, but it is not done.
2. The collector currently assumes `kubectl` availability and some kube-auth story. Do not ignore that.
3. The current chart does not yet include SA/RBAC templates. That gap is real.
4. `python:3.12-slim` is not a real collector runtime for this repo. It needs `kubectl`.
5. `scannerWorker`, `builder`, and `rebuildWorker` are placeholders until backed by approved images.
6. The first dev milestone is not rebuild-and-publish. The first dev milestone is proving the orchestration chain works safely in `argo-hk`.
