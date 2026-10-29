# Local demonstrator walkthrough

Requirements: Docker Engine/Compose, Python 3.12 with the repository virtual environment, and the locked Python packages. Build/install needs access to package/image registries unless already cached. Normal operation after building uses no cloud service. The build script invokes Docker's Node 22 runtime, so a global Node installation is unnecessary.

From the repository root:

```bash
.venv/bin/pip install -e '.[edge,analytics,dev,viz]'
./scripts/edge_build.sh
# Default operational stack exposes only the dashboard on loopback.
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml up -d --no-build
```

Open http://localhost:18780. Read .edge/secrets.json locally and enter the viewer/operator token into the login form. Do not copy secrets into reports. An empty stack shows unknown/unavailable monitoring until measured observations arrive.

The synthetic publisher runs on the host. For host protocol validation/demo access, add the explicit loopback-only overlay:

```bash
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml -f deployment/edge/compose.validation.yaml up -d --no-build
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/edge_demo.py --generate healthy --seed 8500 --output experiments/outputs/phase5-demo-healthy --speed 5 --no-inspections
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/edge_demo.py --generate geometry --seed 8501 --output experiments/outputs/phase5-demo-geometry --speed 5
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/edge_demo.py --generate thermal --seed 8502 --output experiments/outputs/phase5-demo-thermal --speed 5
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/edge_demo.py --generate critical --seed 8503 --output experiments/outputs/phase5-demo-critical --speed 5 --no-inspections
```

Output directories/seeds must be new. Generation uses original TwinGuard sensors; only public observations leave the controller. Each published dataset is replayed with unchanged scientific timestamps, a declared mapped acquisition clock, actual transport receipt and actual processing availability. `--speed 1` is nominal playback, `--speed 5` accelerated. `--step` waits for Enter before each measurement. `--control-file .edge/replay-control.json` accepts a local JSON object with `paused: true/false` for pause/resume. Pausing adjusts the declared playback clock, not recorded original acquisition times.

Watch process charts, select BW-01, inspect B3.1 measurements and thermal pixels, open the event evidence trace, and acknowledge with an operator token. Critical pressure does not wait for LiDAR; the no-inspections command proves that path. Existing critical advisories persist until qualified recovery/review, even after feeds stop. After approximately three source intervals without data, monitoring becomes unavailable rather than inferring healthy status.

For OPC UA, stage only a public manifest plus observations under .edge/opcua-public (no private/scenario directories). Use the controller helper below after generating the healthy demo dataset: 
```bash
.venv/bin/python - <<'PYTHON'
from pathlib import Path
import shutil
source=Path('experiments/outputs/phase5-data-8500')
target=Path('.edge/opcua-public')
target.mkdir(exist_ok=True)
shutil.copy2(source/'manifest.json',target/'manifest.json')
shutil.copytree(source/'observations',target/'observations',dirs_exist_ok=True)
PYTHON
```
The E4 controller uses separately staged original public sensing records. Start the optional services:

```bash
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml --profile demo-opcua up -d --no-build
```

Controlled worker restart and history inspection:

```bash
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml restart fast-worker
.venv/bin/python scripts/edge_browser.py --output experiments/outputs/phase5-browser-check
```

The same named database/artifact volumes must remain attached. `stop`/`start` preserve them; deleting volumes discards the operational history. Changing policies/profile on an existing F1 checkpoint requires a new explicit reassessment namespace. For site review generate a separate environment with `scripts/edge_init.py --profile site-review` and use a separately named Compose project/volumes; do not silently change an existing simulation checkpoint. Site review has unknown clocks/calibration and no approved critical thresholds.

```bash
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml --profile demo-opcua stop
```

No Phase 6 planning or physical control is included.

Failed durable jobs can be retried after fixing the service cause, without editing scientific records:

```bash
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml exec -T api python -m twinguard.edge.admin retry --job-id inspection-e4-public-8240 --rationale 'Reviewed service dependency correction'
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml exec -T api python -m twinguard.edge.admin archive --days 90
```

Retry accepts only failed jobs, records the prior error/attempt count and an administrator audit, and preserves original inputs and receipt/clock metadata. Use an actual failed job ID from your deployment.


## Browser-controlled presets

For the new isolated demo stack use [the final browser walkthrough](FINAL_DEMO_WALKTHROUGH.md). Existing historical CLI examples remain historical; the new page does not execute physical plant control or arbitrary planned flights.
