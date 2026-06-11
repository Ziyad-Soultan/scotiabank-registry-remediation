# Auth And Secrets Notes

This repo does not currently require a Dex/LDAP secret for the demo flow.

## Dex/LDAP

Dex/LDAP is usually used for human authentication into platforms such as Rancher,
Argo UI, or an internal developer portal. That is different from how an Argo
workflow authenticates to read files, mount PVCs, or pull/copy images.

Use the existing Dex/LDAP secret only if the production integration explicitly
needs to authenticate to an API that requires that user-facing identity layer.
Do not copy human-login secrets into this chart by default.

## What The Workflow Likely Needs

The Argo workflows usually need:

- a Kubernetes service account
- RBAC allowing WorkflowTemplate execution and PVC access
- access to the shared PVC or object-store location containing `images.json`
- access to the shared PVC or object-store location containing `scan-metadata.json`
- registry credentials for Red Hat or the internal approved registry mirror
- image pull secret for the approved worker image, if the worker image is private

## Demo Mode

The local demo does not need secrets because it uses checked-in example files and
`refresh_base_family.py --mode dry-run`.

## Execute Mode

Execute mode would need `skopeo` credentials to inspect/copy from the approved
upstream source. Prefer mounting registry auth through a Kubernetes Secret into
the worker container rather than putting credentials in values files.

Typical production pattern:

```text
Kubernetes Secret -> mounted auth file or env var -> skopeo worker -> approved upstream copy
```

Exact secret shape should follow your existing platform standard. If the current
scanner already has a registry/object-store secret, reuse that pattern rather
than inventing a new one.

## Questions To Answer

- Is the Dex/LDAP secret only for UI login, or does a workflow call an API that needs it?
- What service account does the existing scanner workflow use?
- Where are object-store credentials mounted today?
- Where are Red Hat/internal registry credentials mounted today?
- Does the existing hardening process consume an OCI directory, registry ref, or tarball?
