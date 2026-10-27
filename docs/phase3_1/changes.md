# Phase 3.1 repository changes

Original B3 geometry.py and registration.py, plant, sensing and E1 definitions remain unchanged. Changes add the explicitly selected B3.1 module, additive qualified result fields/schemas, combined pipeline/CLI dispatch and optional registration-computation reuse. Restricted evaluator/reporting modules add diagnostics, complete error accounting, paired revalidation and measured figures. Scripts preserve all execution stages, candidate/source/model freeze and deterministic resume. Version is 0.4.1.

Compatibility: prior result records still validate with defaults. New method values require readers to recognize algorithm_version v3.1 and localized_relative measurement_basis. Unqualified raw diagnostics must not enter fusion as calibrated measurements. No final hazard or inspection policy is added.

Files changed/created relative to phase-3 source 775fc11:

- README.md
- configs/experiments/phase3_1/partitions.json
- docs/EXPERIMENTS.md
- docs/GEOMETRIC_CHANGE_DETECTION.md
- docs/PHASE3_1_IMPROVEMENTS.md
- docs/PHASE3_1_ROOT_CAUSE.md
- docs/PHASE3_1_VALIDATION.md
- docs/PHASES.md
- docs/REGISTRATION.md
- docs/TRL_EVIDENCE.md
- docs/figures/phase3_1/01_failure_stages.png
- docs/figures/phase3_1/02_oracle_alignment.png
- docs/figures/phase3_1/03_raw_distributions.png
- docs/figures/phase3_1/04_thresholds.png
- docs/figures/phase3_1/05_patch_scales.png
- docs/figures/phase3_1/06_observability.png
- docs/figures/phase3_1/07_independent_recall.png
- docs/figures/phase3_1/08_examples.png
- docs/phase3_1/api_smoke.json
- docs/phase3_1/b31_calibration_v1.json
- docs/phase3_1/baseline_results.json
- docs/phase3_1/baseline_source.json
- docs/phase3_1/baseline_v1.json
- docs/phase3_1/baseline_v1.sha256
- docs/phase3_1/calibration_inputs_v1.json
- docs/phase3_1/changes.md
- docs/phase3_1/checks.json
- docs/phase3_1/comparison_table.csv
- docs/phase3_1/development_results.json
- docs/phase3_1/diagnostic_results.json
- docs/phase3_1/figure_source_data.json
- docs/phase3_1/final_integrity.json
- docs/phase3_1/heldout_results.json
- docs/phase3_1/improved_freeze.json
- docs/phase3_1/root_cause_checkpoint.json
- docs/phase3_1/trial_table.csv
- pyproject.toml
- schemas/GeometryResult.schema.json
- schemas/PatchEstimate.schema.json
- scripts/phase31.py
- scripts/phase31_baseline_evidence.py
- scripts/phase31_calibrate.py
- scripts/phase31_development.py
- scripts/phase31_generate_development.py
- scripts/phase31_heldout.py
- scripts/phase31_parallel.py
- scripts/phase31_report.py
- scripts/phase31_trace_baseline.py
- src/twinguard/__init__.py
- src/twinguard/analytics/cli.py
- src/twinguard/analytics/geometric_improved.py
- src/twinguard/analytics/pipeline.py
- src/twinguard/core/analytics_contracts.py
- src/twinguard/evaluation/analytics.py
- src/twinguard/evaluation/geometric_diagnostics_report.py
- src/twinguard/evaluation/geometric_figures.py
- src/twinguard/evaluation/geometric_revalidation.py
- src/twinguard/evaluation/geometric_studies.py
- tests/test_phase31.py
