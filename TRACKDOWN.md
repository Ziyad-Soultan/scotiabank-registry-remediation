# Things To Track Down

Use this as a checklist while wiring the prototype to real platform data.

## Rancher

### Running Image Inventory

Find:

- where the current image dump agent runs
- which clusters/environments are included
- where it writes `images.json`
- whether the file is per cluster, per project, per environment, or global
- how often it refreshes
- whether failed/empty namespaces are reported anywhere

Start looking:

- cluster projects/namespaces that run scanner or inventory jobs
- CronJobs, Jobs, or Argo Workflows related to image inventory
- mounted PVCs or object-store credentials in those jobs
- ConfigMaps/Secrets for paths like `images.json`, `image-dump`, `inventory`, `scanner`

Questions to answer:

- Is `images.json` complete for the remediation scope?
- Is there one file per cluster or one combined file?
- Can the remediation workflow read the same PVC/object-store location?
- Is there a stable handoff path we can depend on?

### Argo Runtime Details

Find:

- target namespace for the remediation workflows
- service account name
- whether WorkflowTemplates are allowed
- whether CronWorkflows are allowed
- shared PVC/storage class
- artifact repository configuration
- whether Dex/LDAP is only for human UI login or also used by workflow-called APIs
- existing Secrets used by scanner workflows for object-store or registry auth

Start looking:

- existing Argo namespace
- existing WorkflowTemplates for scanner/reporting
- service account/RBAC used by scanner workflows
- PVCs mounted by current workflows

Questions to answer:

- Should this chart install a PVC, or use an existing one?
- Should the scheduler be CronWorkflow, webhook-triggered workflow, or manually submitted for demo?
- What service account can read scanner handoff files?
- Does any workflow actually need the Dex/LDAP secret, or only Kubernetes service-account credentials?
- How are registry credentials mounted for existing image scan/pull jobs?

## Confluence

### Scanner Pipeline Documentation

Find:

- current Aqua/Trivy workflow docs
- image dump agent docs
- report output docs
- object-store/PVC handoff docs
- any architecture diagram for scanner/reporting

Search terms:

```text
images.json
image dump
cluster image inventory
Aqua
Trivy
scanner workflow
scan metadata
vulnerability report
Argo Workflow
image inventory
```

Questions to answer:

- What scan metadata already exists?
- Is there already a compact JSON summary, or only HTML/CSV/raw Trivy JSON?
- Does scanner metadata include image digest?
- Does scanner metadata include base image lineage or labels?
- Does scanner metadata identify fixable High/Critical counts?

### Approved Base Image Process

Find:

- internal base image standards
- Red Hat source approval process
- approved registry/mirror documentation
- certificate injection process
- hardening process
- image signing/promotion process

Search terms:

```text
golden base image
approved base image
UBI9
OpenJDK
Python 3.11
NGINX
Red Hat registry
internal CA
image hardening
container signing
image promotion
```

Questions to answer:

- Where do approved upstream digests come from?
- Who approves a new Red Hat digest?
- Is the approved artifact pulled directly from `registry.redhat.io` or from an internal mirror?
- What is the input expected by the cert/hardening process?
- Does the hardening process consume an OCI layout, image ref, digest, or tarball?

## Bitbucket

### Scanner And Inventory Code

Find:

- repository for the image dump agent
- repository for scanner workflows
- repository for scanner report parsing
- Helm chart or Argo manifests for current scanner system

Search terms:

```text
images.json
namespaces
epm_code
clusterName
trivy
aqua
scan-metadata
dedupe
image inventory
WorkflowTemplate
CronWorkflow
```

Questions to answer:

- Can we reuse existing workflow templates or service accounts?
- What exact path writes `images.json`?
- What exact path writes scan metadata/report output?
- Is there already a parser we should consume instead of inventing a new metadata format?

### Base Image Build/Hardening Code

Find:

- repo that builds internal UBI/JDK/Python/NGINX images
- cert injection scripts
- Dockerfiles/Containerfiles for golden bases
- promotion pipeline
- registry publish scripts

Search terms:

```text
ubi9
openjdk-17
python-311
nginx-124
certBundle
update-ca-trust
Containerfile
Dockerfile
skopeo
buildah
podman
cosign
promotion
approved
stable
```

Questions to answer:

- What are the real family names?
- What are the internal target repositories?
- Where should `/work/shared/upstream-bases` handoff go?
- Does the downstream process expect source image refs or local OCI directories?
- What labels/annotations must be preserved for audit?

## Data You Need For This Repo

Fill these in as you find them:

```text
Real images.json location:
Real scan metadata location:
Real Argo namespace:
Real service account:
Real PVC or object-store path:
Real skopeo worker image:
Approved upstream source registry:
Internal base image registry:
Approved digest source of truth:
Cert/hardening pipeline repo:
Candidate scan gate:
Publish/signing process:
State tracking location:
```

## Friday Demo Minimum

Minimum viable demo:

- run local dedupe
- run local planner
- show three family plans
- run acquisition dry-run
- show Helm render/lint
- explain production handoff points

Nice to have:

- one real-looking sanitized `images.json`
- one Confluence screenshot or link showing current scanner output
- one Bitbucket link to the existing hardening process
- one answer for where approved digests should come from
