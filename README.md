# TwinGuard

**Development and Validation of an Uncertainty-Aware Industrial IoT Digital Twin for Condition Monitoring and UAV-Assisted Inspection of Boilers and Pressure Equipment**

Phases 0–3 are implemented: plant simulation, imperfect virtual sensing, CPU point-cloud registration, qualified geometric change detection, and calibrated operating/thermal residual analytics. Full synthetic E1/E2 benchmarks are executed. Small-deformation sensitivity remains limited; evidence fusion and industrial safety decisions remain future work. See [Phase 3 validation](docs/PHASE3_VALIDATION.md) for measured results and limitations.

## Install and verify

Validated environment: Ubuntu/Linux, Python 3.12.3. Python 3.11+ is permitted by package metadata but is not independently tested. Version locks target Python 3.12 Linux.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
pip install -e '.[dev,viz,sensing,analytics]' --no-deps
bash scripts/validate.sh
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pip check
```

For a fresh compatible dependency resolution use `pip install -e '.[dev,viz,sensing,analytics]'`. Runtime adds Trimesh; Matplotlib is optional (`.[viz]`) and used for scientific plots. NumPy supplies plant dynamics; the optional analytics extra adds Open3D and SciPy. requirements-analytics.lock pins the analytics runtime. No network is used during simulation after installation.

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

`src/twinguard/core` contains public contracts, time/spatial utilities, schema export and import-boundary auditing. `plant` implements configuration, meshes, baseline, dynamics, faults, snapshots, exports, CLI and scientific plotting. `sensing/read.py` defines a privileged physical read port without sensor acquisition. `evaluation` contains restricted truth contracts and experiment metadata. `api` and `cli` expose implemented features. `analytics` implements public-data inference; `fusion` and `inspection` reserve later responsibilities. Configurations, scenarios, schemas, tests, deployment files, scripts and documentation reside in their named root directories.

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

Generated geometry and synthetic experiments do not establish industrial detection accuracy or TRL 6 for the complete product. This delivery stops at Phase 2.


## Phase 2 virtual sensing

Open3D 0.19.0 CPU RaycastingScene is the preferred backend; an explicit NumPy BVH reference backend is also tested. The optional sensing extra installs Open3D and its substantial dependency stack; the minimal Docker API uses requirements-runtime.lock and stays independent of that stack. requirements-sensing.lock pins the API plus sensing runtime, and requirements-dev.lock captures the full tested development/sensing/plotting environment. Installation/runtime checks target Python 3.12 Linux; Python 3.11 is not independently tested.

```bash
twinguard sensing lidar --scenario scenarios/S2.yaml --time 60 --output-dir output/lidar
twinguard sensing thermal --scenario scenarios/S3.yaml --time 60 --output-dir output/thermal
twinguard sensing iot --scenario scenarios/S1.yaml --output-dir output/iot
twinguard sensing simulate --scenario scenarios/S2.yaml --output-dir output/S2-sensing
twinguard sensing validate --run-dir output/S2-sensing
twinguard sensing visualize --run-dir output/S2-sensing
python scripts/validate_phase2.py --output-dir datasets/synthetic/generated/new-sensing-validation
```

Use `--config configs/sensing/L0.yaml` for ideal verification, L1.yaml for nominal, moderate.yaml for intermediate noise, or L2.yaml for degraded settings. Full scheduled acquisitions use nine configured IoT channels and the existing inspection events. S2 captures at 0 and 60 s are independent raycasts with distinct poses/noise; S5 preserves the historical inspection time. Scenarios are migrated to v3 enabled-sensor lists while old payloads remain readable.

See [virtual sensor interfaces](docs/VIRTUAL_SENSORS.md), [LiDAR](docs/LIDAR_MODEL.md), [thermal](docs/THERMAL_MODEL.md), [IoT](docs/IOT_SENSOR_MODEL.md), and [Phase 2 validation](docs/PHASE2_VALIDATION.md). Public measurements are under observations/; evaluation_private/ holds actual poses, hit identities, modeled reference measurements and evaluator-only plant truth. Phase 3 must use the checksum-validated public loaders in core.observations rather than physical simulator objects. No hidden expected process values, perfect mesh correspondences or point-level semantic truth labels are exported as measurements.

## Analytics and benchmarks

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
twinguard analytics --help
twinguard experiment run E1 --config experiments/E1.yaml --output-dir experiments/outputs/my-E1
twinguard experiment run E2 --config experiments/E2.yaml --output-dir experiments/outputs/my-E2
twinguard experiment report --run-dir experiments/outputs/my-E1
twinguard experiment report --run-dir experiments/outputs/my-E2
```

Add --smoke for a small independent matrix. Use new/empty output directories. Full configurations and results are described in [experiments](docs/EXPERIMENTS.md), [registration](docs/REGISTRATION.md), [geometry](docs/GEOMETRIC_CHANGE_DETECTION.md), [operating analytics](docs/OPERATING_ANALYTICS.md) and [validation](docs/PHASE3_VALIDATION.md). Empty regions or out-of-range/coverage abstentions do not establish healthy equipment.
