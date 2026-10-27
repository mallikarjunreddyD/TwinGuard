# TwinGuard

**Development and Validation of an Uncertainty-Aware Industrial IoT Digital Twin for Condition Monitoring and UAV-Assisted Inspection of Boilers and Pressure Equipment**

Phase 0 infrastructure and Phase 1 physical plant simulation are implemented. The CPU-only, headless modular Python package generates a coherent seven-asset boiler mock-up, load-driven operating states, normal expansion, actual geometric/thermal/process faults, replayable snapshots and isolated ground truth. No sensing, anomaly detection or industrial safety decisions are implemented.

## Install and verify

Validated environment: Ubuntu/Linux, Python 3.12.3. Python 3.11+ is permitted by package metadata but is not independently tested. Version locks target Python 3.12 Linux.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
pip install -e '.[dev,viz]' --no-deps
bash scripts/validate.sh
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pip check
```

For a fresh compatible dependency resolution use `pip install -e '.[dev,viz]'`. Runtime adds Trimesh; Matplotlib is optional (`.[viz]`) and used for scientific plots. NumPy supplies the exact first-order dynamics, so SciPy is unnecessary. No network is used during simulation after installation.

## Run the plant

Output paths must be new or empty; generated data are ignored by Git.

```bash
twinguard plant build --config configs/plant.yaml --output-dir output/plant
twinguard plant simulate --scenario scenarios/S0.yaml --output-dir output/S0
twinguard plant simulate --scenario scenarios/S2.yaml --output-dir output/S2
twinguard plant snapshot --run-dir output/S2 --time 60 --format glb
twinguard plant snapshot --run-dir output/S2 --time 45.5 --format ply
twinguard plant visualize --run-dir output/S2 --time 60
twinguard plant inspect --run-dir output/S2
python scripts/validate_phase1.py --output-dir datasets/synthetic/generated/my-validation
```

The last command executes S0–S5 plus a support-shift demonstration, compares actual numerical geometry to analytical references and generates PNG/GLB/PLY/JSON/NPZ artifacts. Each run has baseline/, snapshots/, operating_states.json, manifest.json, and restricted/ labels/controller configuration. Visualization commands require the optional viz extra. All plots are labeled **simulation ground truth**, not anomaly detection.

Original commands remain: `twinguard doctor`, `version`, `list-scenarios`, `validate-config scenarios/S2.yaml`, `validate-data datasets/synthetic/observation.json --kind SensorObservation`, and `export-schemas`. Use `twinguard --root /path/to/TwinGuard ...` outside the repository; explicit CLI input paths are relative to the invoking directory.

## API and container

```bash
uvicorn twinguard.api.app:app --reload --host 127.0.0.1 --port 8000
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/version
curl --fail http://127.0.0.1:8000/capabilities
docker compose --env-file .env.example -f deployment/compose.yaml config
docker compose --env-file .env.example -f deployment/compose.yaml up --build --wait
# After inspection:
docker compose -f deployment/compose.yaml down
```

The minimal API exposes health, version and capability inventory. Docker requires no GPU, serves no datasets or truth files and omits optional plotting libraries. The API does not run analytics or return truth-state objects.

## Repository and roadmap

`src/twinguard/core` contains public contracts, time/spatial utilities, schema export and import-boundary auditing. `plant` implements configuration, meshes, baseline, dynamics, faults, snapshots, exports, CLI and scientific plotting. `sensing/read.py` defines a privileged physical read port without sensor acquisition. `evaluation` contains restricted truth contracts and experiment metadata. `api` and `cli` expose implemented features. `analytics`, `fusion`, and `inspection` reserve later responsibilities. Configurations, scenarios, schemas, tests, deployment files, scripts and documentation reside in their named root directories.

| Phase | Scope |
|---|---|
| 0 | Architecture, data contracts, and development environment |
| 1 | Industrial plant digital twin and fault simulation |
| 2 | Virtual LiDAR, thermal, and IoT sensing |
| 3 | Registration, geometric change detection, and operating-state analytics |
| 4 | Hazard-aware and temporally consistent evidence fusion |
| 5 | Edge platform, industrial communication, and dashboard |
| 6 | Risk-adaptive inspection and viewpoint planning |
| 7 | Experimental validation and TRL evidence package |

See [plant model](docs/PLANT_MODEL.md), [physics](docs/PHYSICS_MODEL.md), [faults](docs/FAULT_INJECTION.md), [Phase 1 validation](docs/PHASE1_VALIDATION.md), [contracts](docs/DATA_CONTRACTS.md), [architecture](docs/ARCHITECTURE.md), [scenarios](docs/SCENARIOS.md), [experiments](docs/EXPERIMENTS.md), [phase gates](docs/PHASES.md), [limitations](docs/ASSUMPTIONS_AND_LIMITATIONS.md), and [evidence](docs/TRL_EVIDENCE.md). Phase 0 historical results remain in docs/VALIDATION.md.

Generated geometry and synthetic experiments do not establish industrial detection accuracy or TRL 6 for the complete product. This delivery stops at Phase 1.
