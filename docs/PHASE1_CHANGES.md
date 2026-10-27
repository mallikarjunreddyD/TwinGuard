# Phase 1 file inventory

Prepared against the clean Phase 0 baseline. No unrelated changes existed before implementation. No files were removed. Full generated datasets/models are Git-ignored; the small figures and measured JSON under docs/ are intentional review artifacts. Changes are left in the working tree for review; no commit or push was made.

## Created

- configs/plant.yaml
- configs/profiles/P0.yaml
- configs/profiles/P1.yaml
- configs/profiles/P2.yaml
- configs/profiles/P3.yaml
- configs/profiles/P4.yaml
- docs/FAULT_INJECTION.md
- docs/PHASE1_CHANGES.md
- docs/PHASE1_VALIDATION.md
- docs/PHYSICS_MODEL.md
- docs/PLANT_MODEL.md
- docs/figures/phase1_ground_truth.png
- docs/figures/phase1_operating_traces.png
- docs/phase1_validation.json
- schemas/PlantConfig.schema.json
- schemas/SimulationManifest.schema.json
- schemas/restricted/GroundTruthSnapshot.schema.json
- scripts/validate_phase1.py
- src/twinguard/core/boundaries.py
- src/twinguard/plant/cli.py
- src/twinguard/plant/config.py
- src/twinguard/plant/contracts.py
- src/twinguard/plant/dynamics.py
- src/twinguard/plant/faults.py
- src/twinguard/plant/geometry.py
- src/twinguard/plant/io.py
- src/twinguard/plant/model.py
- src/twinguard/plant/simulator.py
- src/twinguard/plant/visualize.py
- src/twinguard/sensing/read.py
- tests/test_phase1.py

## Modified

- .gitignore
- README.md
- configs/assets.yaml
- configs/sensors.yaml
- datasets/ground_truth/fault-S2.yaml
- datasets/ground_truth/fault-S3.yaml
- datasets/ground_truth/fault-S4.yaml
- datasets/ground_truth/fault-S5.yaml
- docs/ARCHITECTURE.md
- docs/ASSUMPTIONS_AND_LIMITATIONS.md
- docs/DATA_CONTRACTS.md
- docs/EXPERIMENTS.md
- docs/PHASES.md
- docs/SCENARIOS.md
- docs/TRL_EVIDENCE.md
- pyproject.toml
- requirements-dev.lock
- requirements-runtime.lock
- scenarios/S0.yaml
- scenarios/S1.yaml
- scenarios/S2.yaml
- scenarios/S3.yaml
- scenarios/S4.yaml
- scenarios/S5.yaml
- schemas/ExperimentDefinition.schema.json
- schemas/ExperimentRun.schema.json
- schemas/SensorConfiguration.schema.json
- schemas/restricted/FaultInjection.schema.json
- scripts/lock_dependencies.py
- src/twinguard/__init__.py
- src/twinguard/api/app.py
- src/twinguard/cli/__init__.py
- src/twinguard/core/contracts.py
- src/twinguard/core/registry.py
- src/twinguard/evaluation/contracts.py
- tests/test_phase0.py

## Removed

None.
