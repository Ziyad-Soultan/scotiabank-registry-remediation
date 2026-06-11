# Architecture Flow

This diagram shows the demo and target production flow at a high level.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"background": "#1e1e2e", "primaryTextColor": "#cdd6f4", "lineColor": "#cdd6f4", "fontFamily": "Inter, ui-sans-serif, system-ui, sans-serif"}}}%%
flowchart LR
  A["Prod-shaped images.json<br/>running image inventory"] --> B["inventory-dedup<br/>deduplicate_image_records.py"]
  B --> C["unique-images.json<br/>one runtime artifact per image"]
  B --> D["sightings.json<br/>all clusters/namespaces preserved"]

  E["Aqua/Trivy scan metadata<br/>compact vuln summary"] --> F["scan metadata planner<br/>plan_base_refresh_from_scan_metadata.py"]
  C --> F
  G["base family catalog<br/>approved upstream + digest"] --> F

  F --> H["image-evaluations.json<br/>per-image decision trail"]
  F --> I["family-refresh-plans.json<br/>one plan per base family"]
  F --> J["family-refresh-summary.json<br/>demo-friendly rollup"]
  F --> R["family-acquisition-fanout.min.json<br/>minimal family + upstream payload"]

  R --> K["refresh-base-family<br/>refresh_base_family.py"]
  K --> L["dry-run output<br/>validated skopeo inspect/copy commands"]
  K -. "execute mode later" .-> M["OCI handoff path<br/>/work/shared/upstream-bases"]

  M --> N["existing cert injection<br/>and hardening process"]
  N --> O["candidate internal base image"]
  O --> P["post-build scan gate"]
  P --> Q["internal registry publish"]

  classDef input fill:#313244,stroke:#89b4fa,color:#cdd6f4
  classDef process fill:#1e1e2e,stroke:#a6e3a1,color:#cdd6f4
  classDef output fill:#181825,stroke:#f9e2af,color:#cdd6f4
  classDef handoff fill:#181825,stroke:#cba6f7,color:#cdd6f4
  classDef later fill:#11111b,stroke:#f38ba8,color:#cdd6f4

  class A,E,G input
  class B,F,K process
  class C,D,H,I,J,L,R output
  class M,N handoff
  class O,P,Q later
```

## What Runs In The Demo

The demo runs:

- inventory dedupe
- scan metadata planning
- family-level refresh plan generation
- upstream acquisition dry-run

The demo does not run:

- real Red Hat pull
- cert injection
- hardening
- image rebuild
- final candidate scan
- internal registry push
- cluster mutation

## Safety Boundary

The current acquisition worker only proves the control-plane decision:

```text
family -> approved upstream image -> pinned digest -> handoff path
```

It defaults to `dry-run`, so it emits the exact `skopeo inspect` and `skopeo copy`
commands it would use later without copying anything.
