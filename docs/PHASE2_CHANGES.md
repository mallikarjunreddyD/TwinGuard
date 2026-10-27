# Phase 2 change inventory

Branch phase-2-virtual-sensing starts at phase-1-plant-simulator (105bc0e). The starting tree was clean; no unrelated changes were overwritten. Source changes are left in the working tree for review; no commit or push was made. Full generated datasets remain ignored. The small docs figures/report are intentional review artifacts.

## Created

- configs/sensing/L0.yaml
- configs/sensing/L1.yaml
- configs/sensing/L2.yaml
- configs/sensing/moderate.yaml
- docs/IOT_SENSOR_MODEL.md
- docs/LIDAR_MODEL.md
- docs/PHASE2_CHANGES.md
- docs/PHASE2_VALIDATION.md
- docs/THERMAL_MODEL.md
- docs/VIRTUAL_SENSORS.md
- docs/figures/phase2_coverage.png
- docs/figures/phase2_iot.png
- docs/figures/phase2_lidar.png
- docs/figures/phase2_scan_comparison.png
- docs/figures/phase2_thermal.png
- docs/phase2_sensing_validation.json
- requirements-sensing.lock
- schemas/AcquisitionConfig.schema.json
- schemas/ObservationManifest.schema.json
- scripts/validate_phase2.py
- src/twinguard/core/observations.py
- src/twinguard/evaluation/sensing.py
- src/twinguard/sensing/acquisition.py
- src/twinguard/sensing/cli.py
- src/twinguard/sensing/config.py
- src/twinguard/sensing/export.py
- src/twinguard/sensing/iot.py
- src/twinguard/sensing/lidar.py
- src/twinguard/sensing/noise.py
- src/twinguard/sensing/products.py
- src/twinguard/sensing/raycast.py
- src/twinguard/sensing/thermal.py
- src/twinguard/sensing/visualize.py
- tests/test_phase2_geometry.py
- tests/test_phase2_integration.py
- tests/test_phase2_iot.py

## Modified

- README.md
- configs/sensors.yaml
- docs/ARCHITECTURE.md
- docs/ASSUMPTIONS_AND_LIMITATIONS.md
- docs/DATA_CONTRACTS.md
- docs/PHASES.md
- docs/SCENARIOS.md
- docs/TRL_EVIDENCE.md
- pyproject.toml
- requirements-dev.lock
- scenarios/S0.yaml
- scenarios/S1.yaml
- scenarios/S2.yaml
- scenarios/S3.yaml
- scenarios/S4.yaml
- scenarios/S5.yaml
- schemas/InspectionCapture.schema.json
- schemas/SensorObservation.schema.json
- scripts/lock_dependencies.py
- src/twinguard/__init__.py
- src/twinguard/api/app.py
- src/twinguard/cli/__init__.py
- src/twinguard/core/boundaries.py
- src/twinguard/core/contracts.py
- src/twinguard/core/registry.py
- src/twinguard/plant/simulator.py
- src/twinguard/sensing/read.py

## Removed

None.
