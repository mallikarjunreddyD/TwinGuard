# TwinGuard

Development and Validation of an Uncertainty-Aware Industrial IoT Digital Twin for Condition Monitoring and UAV-Assisted Inspection of Boilers and Pressure Equipment.

Phase 0 implements architecture, versioned contracts, configuration validation, spatial/time utilities, evaluation metadata, API/CLI and validation infrastructure. Algorithms in Phases 1–7 are pending. Synthetic configuration fixtures are not physical validation or evidence of a complete TRL 6 system.

## Install and validate (Ubuntu, Python 3.12 validated)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
pip install -e '.[dev]' --no-deps
bash scripts/validate.sh
twinguard version
twinguard doctor
twinguard list-scenarios
twinguard validate-config scenarios/S2.yaml
twinguard validate-data datasets/synthetic/observation.json --kind SensorObservation
twinguard export-schemas
pytest -q
```

The version locks capture the tested Python 3.12 Linux environment. For another supported Python version (3.11+), resolve compatible versions with `pip install -e ".[dev]"` and rerun validation.

Commands default to the current repository root; use `twinguard --root /path/to/TwinGuard ...` from another directory. The package is named `twinguard`; the existing workspace directory name is preserved.

## Run

```bash
uvicorn twinguard.api.app:app --reload --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/version
curl http://127.0.0.1:8000/capabilities
```

Production container (CPU only):

```bash
docker compose --env-file .env.example -f deployment/compose.yaml config
docker compose --env-file .env.example -f deployment/compose.yaml up --build -d
curl --fail http://127.0.0.1:8000/health
docker compose -f deployment/compose.yaml down
```

The API image runs as a non-root user, has an HTTP health check and contains no datasets or ground truth. Only metadata endpoints exist. The configurable host port defaults to 8000 and binds to loopback.

## Repository

`src/twinguard/core` holds public contracts, configuration loading, schema export, serialization, rigid transforms and UTC utilities. `evaluation` holds restricted faults, experiment definitions/run metadata and the evaluator protocol. `api` and `cli` expose implemented infrastructure. `plant`, `sensing`, `analytics`, `fusion`, and `inspection` reserve later module boundaries. `configs`, `scenarios`, `datasets`, `experiments`, `schemas`, `tests`, `deployment`, `docs`, and `scripts` contain their corresponding fixtures and infrastructure.

See [architecture](docs/ARCHITECTURE.md), [contracts](docs/DATA_CONTRACTS.md), [scenarios](docs/SCENARIOS.md), [experiments](docs/EXPERIMENTS.md), [phase gates](docs/PHASES.md), [evidence register](docs/TRL_EVIDENCE.md), and [limitations](docs/ASSUMPTIONS_AND_LIMITATIONS.md). Actual verification is recorded in docs/VALIDATION.md.

## Roadmap

0. Contracts and validation infrastructure (this implementation).
1. Plant geometry, operating profiles and controlled fault injection.
2. Virtual sensing and real/public-source adapters.
3. Registration and condition-aware analytics.
4. Temporal, hazard-aware evidence fusion.
5. Inspection prioritization and viewpoint planning.
6. Edge application integration and dashboard.
7. Independent, physical and relevant-environment validation.

Phase 1 starts by consuming `configs/assets.yaml`, `configs/sensors.yaml`, `configs/system.yaml`, `scenarios/S0–S5.yaml`, restricted fault configurations and the exported schemas. Add simulator implementations behind these contracts; emit public observations and private labels through separate paths. Do not add hidden labels to public records. No Phase 1 simulator is included here.
