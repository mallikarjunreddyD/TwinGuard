# Phase 3 changes

Branch phase-3-analytics; no commits or pushes made. No files removed.

Analytics modules implement validated cloud loading, ICP, qualified geometric regions, healthy-only operating fits, numeric thermal residuals, evidence conversion and CLI. Evaluator modules implement restricted observability, sealed post-inference scoring, reproducible E1/E2 batches and measured plots. Core adds versioned result contracts and exports. Sensing changes correct saturation and private ray accounting. Optional analytics dependencies and a lock are added; the minimal API stays independent. Existing tests change only maturity assertions for now-implemented E1/E2/registration.

Compatibility: public schema version remains 1.0.0; new public result schemas are additive. Thermal writers add two mask/status arrays, while loaders accept old two-array records. Legacy thermal quantitative inference abstains. Existing observation scalar fields and plant/sensing commands remain supported. Readers that insist on the old exact NPZ key set must adopt the new saturation/status fields.

## Created

- configs/analytics/accepted_reference.json
- configs/analytics/default.yaml
- configs/experiments/E1-smoke.yaml
- configs/experiments/E1.yaml
- configs/experiments/E2-smoke.yaml
- configs/experiments/E2.yaml
- docs/GEOMETRIC_CHANGE_DETECTION.md
- docs/OPERATING_ANALYTICS.md
- docs/PHASE3_CHANGES.md
- docs/PHASE3_VALIDATION.md
- docs/REGISTRATION.md
- docs/figures/phase3_E1_comparison.png
- docs/figures/phase3_E1_observability.png
- docs/figures/phase3_E1_patch_quality.png
- docs/figures/phase3_E2_comparison.png
- docs/figures/phase3_E2_operating_residuals.png
- docs/figures/phase3_E2_thermal_residuals.png
- docs/phase3_api_smoke.json
- docs/phase3_checks.json
- docs/phase3_e1_results.json
- docs/phase3_e2_results.json
- docs/phase3_scenario_smoke.json
- requirements-analytics.lock
- schemas/AnalyticsConfig.schema.json
- schemas/ExperimentBenchmark.schema.json
- schemas/GeometryRegion.schema.json
- schemas/GeometryResult.schema.json
- schemas/OperatingPrediction.schema.json
- schemas/PatchEstimate.schema.json
- schemas/RegistrationResult.schema.json
- schemas/ThermalRegion.schema.json
- schemas/ThermalResult.schema.json
- src/twinguard/analytics/cli.py
- src/twinguard/analytics/clouds.py
- src/twinguard/analytics/config.py
- src/twinguard/analytics/evidence.py
- src/twinguard/analytics/geometry.py
- src/twinguard/analytics/operating.py
- src/twinguard/analytics/pipeline.py
- src/twinguard/analytics/reference.py
- src/twinguard/analytics/registration.py
- src/twinguard/analytics/thermal.py
- src/twinguard/core/analytics_contracts.py
- src/twinguard/evaluation/analytics.py
- src/twinguard/evaluation/cli.py
- src/twinguard/evaluation/experiments.py
- src/twinguard/evaluation/observability.py
- src/twinguard/evaluation/visualize.py
- tests/test_phase3_integrity.py
- tests/test_phase3_units.py

## Modified

- README.md
- docs/ARCHITECTURE.md
- docs/ASSUMPTIONS_AND_LIMITATIONS.md
- docs/DATA_CONTRACTS.md
- docs/EXPERIMENTS.md
- docs/LIDAR_MODEL.md
- docs/PHASES.md
- docs/THERMAL_MODEL.md
- docs/TRL_EVIDENCE.md
- experiments/E1.yaml
- experiments/E2.yaml
- pyproject.toml
- schemas/ExperimentDefinition.schema.json
- scripts/lock_dependencies.py
- src/twinguard/__init__.py
- src/twinguard/analytics/__init__.py
- src/twinguard/api/app.py
- src/twinguard/cli/__init__.py
- src/twinguard/core/observations.py
- src/twinguard/core/registry.py
- src/twinguard/evaluation/contracts.py
- src/twinguard/sensing/export.py
- src/twinguard/sensing/lidar.py
- src/twinguard/sensing/thermal.py
- tests/test_phase0.py

Generated large datasets, model artifacts and predictions remain under ignored experiments/outputs and output; this inventory lists deliverable repository files.
