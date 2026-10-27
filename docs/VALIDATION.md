# Phase 0 validation record

Executed on 27 October 2026 using Python 3.12.3 on Linux. TwinGuard 0.1.0; schema 1.0.0. Exact runtime/development versions are committed in requirements-runtime.lock and requirements-dev.lock. No Phase 1–7 algorithms or scientific performance experiments were executed.

| Check | Actual result |
|---|---|
| Editable package installation with development extras | Passed in .venv |
| pip check | No broken requirements |
| bash scripts/validate.sh with .venv on PATH | Passed |
| Pytest | 54 passed, 1 upstream deprecation warning |
| Ruff lint | Passed for src, tests and dependency-lock script |
| Ruff format check | 23 files already formatted |
| Mypy | Success: no issues in 21 source files; Python 3.12 target |
| JSON Schema export and committed-schema comparison | Passed; 13 public/config schemas and 1 restricted schema |
| S0–S5 scenario validation | All six passed, including catalog and fault references |
| CLI doctor/version/list/validate/export | Passed; invalid config subprocess returns exit code 1 |
| Live Uvicorn HTTP smoke | /health, /version, /capabilities responded correctly; process stopped |
| Docker Compose configuration | Validated with .env.example |
| Final Docker image build | Passed using deployment/Dockerfile and pinned runtime requirements |
| Compose API startup and Docker health check | Healthy; local HTTP endpoints verified; temporary stack removed |

The warning originates from the installed FastAPI/Starlette test client: HTTPX support is deprecated in favor of HTTPX2. The current HTTPX test path works; migration is a future dependency-maintenance task. No test failures remain.

The standard shell sandbox could not launch because bubblewrap was unavailable. Commands ran through the approved shell execution path. PyPI downloads were unusually slow. The successful Docker build used the Dockerfile's optional PIP_FIND_LINKS/PIP_NO_INDEX build arguments against a temporary loopback-only mirror of cached dependency wheels, with host networking for build-time access. The container itself uses its normal Compose network. The temporary wheel server and API services were stopped after validation. The ordinary online Compose build command below is documented; no successful claim is made for online download performance.

Reproduce the normal development checks:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
pip install -e '.[dev]' --no-deps
bash scripts/validate.sh
pip check
ruff format --check src tests scripts/lock_dependencies.py
```

Validate/start a CPU-only deployment with normal online dependency resolution:

```bash
docker compose --env-file .env.example -f deployment/compose.yaml config
docker compose --env-file .env.example -f deployment/compose.yaml up --build --wait --wait-timeout 90
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/version
curl --fail http://127.0.0.1:8000/capabilities
docker compose -f deployment/compose.yaml down
```

The verified build command used an ephemeral mirror, not a required project service:

```bash
docker build --network host \
  --build-arg PIP_FIND_LINKS=http://127.0.0.1:18765 \
  --build-arg PIP_NO_INDEX=1 \
  -f deployment/Dockerfile -t twinguard-phase0:validation .
```

Do not use that mirror URL unless a matching local wheel server has been deliberately started. No datasets, generated metrics, hardware validation, real accuracy figures or TRL ratings are implied by these infrastructure checks. Python 3.11 is allowed by the project but was not tested; the supplied locks and type-check target describe Python 3.12.
