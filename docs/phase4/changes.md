# Phase 4 change inventory

Starting commit: d99075f. Branch: phase-4-evidence-fusion.

- `src/twinguard/fusion/`: contracts, adapters, policies, temporal/spatial/dependence checks, pure assessment/replay, event lifecycle, sealed I/O and CLI.
- `src/twinguard/evaluation/fusion_{scenarios,experiments,metrics,report}.py`: controlled evidence, actual upstream E3, independent matching and measured figures/audits.
- `configs/fusion/`: illustrative hazards, uncalibrated site template, frozen healthy models and original public historical observations.
- `configs/experiments/E3.yaml`, `experiments/E3.yaml`: reproducible final and separate development seeds.
- Core registry/schema exports, root/evaluation CLI, API phase/version and package version: additive integration; prior ConditionAssessment schema preserved.
- `tests/test_phase4.py`: 57 Phase 4 tests. Prior 170 regression tests retained; Phase 0 maturity expectations updated.
- `docs/PHASE4_VALIDATION.md`: complete A–J report and all 34 acceptance decisions. Six fusion guides, existing architecture/experiment/evidence-register updates, seven figures and compact numerical artifacts accompany it.

No changes to the plant, sensing or analytics algorithms versus d99075f. Raw experiment outputs remain locally reproducible under experiments/outputs and ignored by Git; compact results and audited CLI examples are committed. No Phase 5, live notifications, control-system writes or deployment safety certification.
