# Examples

- `collected-image-records.example.json` now shows the **current nested `images.json` format** from the cluster image dump agent (`epm_code -> namespaces -> images`). `scripts/deduplicate_image_records.py` expands this automatically.
- `trivy-report.example.json` shows the shape expected by `scripts/filter_trivy_actionable.py`.
- `trivy-scan-metadata.example.json` shows raw Trivy JSON converted into the standard compact `scan-metadata/v1` contract by `scripts/trivy_to_scan_metadata.py`.
- `unique-images-for-refresh.example.json` shows the deduplicated runtime artifact shape that feeds metadata-driven refresh planning.
- `scan-metadata.example.json` shows the compact scanner metadata shape expected by `scripts/plan_base_refresh_from_scan_metadata.py`.
- `output/` contains sample dedupe outputs.
- `actionable-output/` contains sample filtered Trivy outputs.
