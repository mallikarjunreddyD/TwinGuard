# Experiment E4 — actual local platform integration

E4 measures software-loopback communication, durable processing, recovery, API and browser delivery on the available CPU workstation. It is not field latency, hardware validation, 24-hour endurance or 90-day retention evidence. Phases E1–E3 and their numerical algorithms/results are unchanged.

The controller is scripts/run_e4.py. It uses real Mosquitto QoS 1, PostgreSQL, separate fast/Open3D workers, the existing F1 implementation, FastAPI/Nginx, Chromium and numeric OPC UA. It never sends evaluator-only state into runtime services. Fresh public sensing seeds 8200–8242 are separate from development 8100–8104. Three independent normal and critical source runs are configured; failure profiles are targeted single controlled interruptions, not population reliability estimates.

B0 is a pre-platform offline F1 computation reference, not transport delay. B1 includes a sustained approximately one-minute paced source run and repeated normal streams. B2 accelerates volume. B3 sends duplicates/out-of-order records. B4 restarts worker/API/database with committed history comparisons. B5 interrupts broker and OPC UA. B6 waits for source staleness and processes actual degraded L2 scans. B7 publishes critical pressure without UAV. B8 uploads actual LiDAR/thermal arrays and runs unchanged analytics. B9 executes the browser views, real model rendering, evidence, acknowledgment and reconnect.

## Execution

Build with scripts/edge_build.sh. Stop another stack using the same loopback validation ports, preserving its volumes. Start a fresh named project for formal evaluation:

```bash
docker compose --env-file .edge/runtime.env -p twinguard-e4 -f deployment/compose.yaml -f deployment/edge/compose.validation.yaml up -d --no-build
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/run_e4.py --output experiments/outputs/my-E4
```

The output must not exist. The controller uses project twinguard-e4 by default for controlled service interruptions; --project selects a dedicated E4 project. The optional OPC UA profile requires the staged public observations directory described in DEMO_WALKTHROUGH.md. Large raw results stay under ignored experiments/outputs; compact metrics/plots/screenshots are committed in docs/phase5 and docs/figures/phase5.

## Measurement rules

Publisher IDs, emission/PUBACK times, original/mapped acquisition, actual edge receipt, SQL jobs, computation boundaries, confirmed advisory commit, API samples and browser visibility are preserved. Completeness compares distinct published observation identities with SQL records, excluding deliberate retransmission inflation. Broker PUBACK is not database completeness. Source/model time is not replaced by assumed service availability.

Software timings use wall UTC boundaries for cross-process events and monotonic clocks for durations. On this single host they share its software clock; no distributed/hardware timestamp accuracy is claimed. Ingest rows commit after their recorded receipt; final job timing includes an observed post-commit confirmation. Browser/API visibility is observed separately. IoT and inspection paths are reported separately. Quantiles include sample counts; small-n browser/failure observations are not given misleading statistical confidence.

Resource sampling records actual Docker CPU/memory, pending/processing jobs, PostgreSQL bytes, SQL/API response durations and timestamps. Estimates of 90-day capacity use measured bytes/rate and explicitly exclude unmeasured long-run growth behavior. OPC UA is polled snapshot acquisition; completeness is not asserted against every simulator write.

Predictions/public operational snapshots are saved and hashed before any optional private evaluation. No scenario-to-status mapping is used. Original failed/development runs are preserved, never overwritten. See PHASE5_VALIDATION.md for actual executed results, failure details, deployment limitations and each acceptance criterion.

The existing CLI also dispatches E4: `twinguard experiment run E4 --config experiments/E4.yaml --output-dir experiments/outputs/my-E4 --project twinguard-e4`. Report generation is `twinguard experiment report --run-dir experiments/outputs/my-E4`. These require the repository scripts and the running local deployment.
