# Prod integration gap list

This is the blunt list of what still needs real production details or copied logic before this scaffold becomes an actual Scotiabank-ready remediation control plane.

## 1. Runtime inventory generation (`images.json` producer)
Current state:
- The repo can now collect runtime inventory directly from configured prod clusters using `scripts/collect_cluster_images.py`.
- It can still consume one prod-shaped `images.json` file or a directory of per-cluster JSON files.
- The Helm chart now includes a collection workflow that writes one `*.images.json` file per cluster before dedupe.

You still need to provide from the existing repo/platform:
- the real prod cluster list / kubectl contexts / service-account RBAC
- the exact trigger model (CronJob, Argo Workflow, DaemonSet, one-shot job, etc.)
- the exact output contract if it differs from the currently assumed nested shape
- any cluster/environment naming fields that must be preserved in the JSON
- the real handoff location per cluster (PVC, object store, artifact repo, etc.)
- any namespace scoping/exclusion rules required by prod

## 2. Scanner auth and execution model
Current state:
- `scan_unique_images.py` can run real `trivy image` scans in `execute` mode.
- There is **no** Aqua login/auth/session logic in this repo today.
- There is **no** private-registry auth wiring in the chart today.

You need to provide from prod/existing repos:
- whether scans should run through Aqua, Trivy directly, or Aqua-managed Trivy
- registry auth method for pulling private images during scan
- any required `dockerconfigjson` / robot account / pull secret names
- any Aqua API endpoint, credentials, scanner group, or policy IDs if Aqua is the required control plane
- whether Trivy DB access must use an internal mirror/proxy instead of public internet
- whether prod requires offline DB bundles or internal OCI DB mirrors
- scanner CLI flags/policies that must be enforced in prod

## 3. `images.json` storage and workflow handoff
Current state:
- Helm expects per-cluster inventory files to already exist at `inventory.clusterImageInventoryPath`.
- The dedupe child copies outputs into the shared workflow PVC.

You need to provide:
- the real shared path or artifact handoff path used in prod
- whether inventory arrives on PVC, object storage, NFS, git, or Argo artifacts
- retention policy for raw per-cluster inventory files
- whether old files must be pruned before the next run
- whether one orchestrator run should process all clusters or one environment at a time

## 4. Lineage mapping: app image -> managed base family
Current state:
- The planner only works reliably if images can be mapped back to a managed internal base family.
- Example catalog matching is still simplistic and selector-based.

You need to provide:
- the real lineage source of truth
- whether base family comes from image labels, build metadata, registry metadata, repo metadata, or a manual mapping file
- the exact labels/annotations if they already exist in built images
- the real family catalog entries for each managed base line
- the fallback behavior when lineage is missing or ambiguous

## 5. Base-family catalog
Current state:
- The catalog is still example data with example digests and a few family stubs.
- Red Hat is modeled as the approved upstream source for now.

You need to provide:
- the real managed base family list
- real target repositories in the internal registry
- approved upstream image names
- approved pinned digests
- any family-specific customization profile names
- publication tag policy per family
- policy on whether unpinned upstream is ever allowed

## 6. Upstream acquisition worker
Current state:
- `refresh_base_family.py` validates allowlisted upstream registries/types.
- In execute mode it expects `skopeo` to exist.
- It only performs the acquisition/handoff step.

You need to provide:
- the real internal worker image containing `python3` + `skopeo`
- Red Hat auth method if required in prod
- any internal mirror registry rules that should replace direct `registry.redhat.io`
- TLS/cert bundle requirements for registry access
- whether acquisition should copy to OCI layout, tarball, or another corporate-standard format

## 7. Rebuild / cert / hardening logic
Current state:
- This is still placeholder-only.
- `rebuild_family_candidate.py` only emits a handoff JSON contract.

You need to copy in or define:
- the real rebuild script or workflow from the work repo
- cert injection logic
- hardening logic
- package install/update logic
- build engine choice (`buildah`, `podman`, Kaniko, Tekton, etc.)
- required secrets/certs/config mounts
- push logic to candidate registry
- immutable tag generation logic
- digest capture after push

## 8. Verification / republish gates
Current state:
- No real candidate rescan/publish gate is wired yet.

You need to provide:
- the real post-build scan step
- pass/fail thresholds used by prod
- promotion logic from candidate -> approved/stable tags
- signing requirements
- attestation/SBOM requirements if any
- rollback behavior when verification fails

## 9. Helm values that must be replaced
These are still placeholders and must be set with real prod values:
- `namespace`
- `serviceAccount.name`
- `argo.artifactRepository.bucketOrPath`
- `argo.pvc.claimName`
- `argo.pvc.storageClassName`
- `schedule.cron`
- `images.scannerWorker.repository`
- `images.scannerWorker.tag`
- `images.builder.repository`
- `images.builder.tag`
- `images.rebuildWorker.repository`
- `images.rebuildWorker.tag`
- `publication.candidateRegistry`
- `rebuild.workRepoPath`

## 10. Supporting config files that need real prod content
- `config/base-family-catalog.example.json`
- `config/source-locations.example.yaml`
- `config/ownership-map.example.yaml`

## 11. Operational policy questions you still need to decide
- one global run across all prod clusters vs one run per cluster/environment?
- should the scanner stage happen in this repo or should this repo consume existing prod metadata only?
- should Red Hat be hit directly or through an internal approved mirror?
- who owns approval of new upstream digests?
- who gets notified when a family refresh is planned or blocked?
- what is the cooldown window to avoid repeated rebuilds for the same family?
- how should family state/history be stored?

## 12. What is already real vs fake
Real now:
- multi-cluster `images.json` ingestion
- dedupe of repeated runtime sightings
- Trivy execution support in the scan helper script
- compact `scan-metadata/v1` output generation
- Helm chart renders successfully with concrete override values

Still fake / scaffold:
- cluster-side inventory collection
- Aqua login/integration
- private registry auth wiring
- real lineage mapping
- real base-family catalog
- real rebuild/cert/hardening logic
- candidate rescan + promotion gate
- production secrets and worker images
