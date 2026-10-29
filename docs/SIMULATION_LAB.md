# Simulation Lab

The optional lab publishes **public synthetic observations** into an isolated TwinGuard edge deployment. It provides no physical plant or UAV control. It is not a new scientific detector/planner evaluation.

## Install once, then demonstrate in the browser

Use the isolated worktree `/home/mallikarjun/workspace/TwinGuard-demo-ux`, branch `phase-7-demo-ux-finalization`. Its source is outside the original release archive roots. Installation requires the existing Docker/Compose and package/image prerequisites; runtime has no cloud dependency.

```bash
cd /home/mallikarjun/workspace/TwinGuard-demo-ux
python3 scripts/demo_init.py --profile simulation
docker compose -p twinguard-demo-ux --env-file .edge/runtime.env \
  -f deployment/compose.yaml -f deployment/edge/compose.demo-ux.yaml \
  build api inspection-worker frontend
# Build the privileged controller after its local analytics base image exists.
docker compose -p twinguard-demo-ux --env-file .edge/runtime.env \
  -f deployment/compose.yaml -f deployment/edge/compose.demo-ux.yaml \
  build simulation-controller
docker compose -p twinguard-demo-ux --env-file .edge/runtime.env \
  -f deployment/compose.yaml -f deployment/edge/compose.demo-ux.yaml up -d
```

Open `http://localhost:19380`. Obtain the appropriate local token from the ignored `.edge/secrets.json`; tokens are never embedded in documentation. Installation is for a **fresh isolated Compose project**. An existing database requires authorized role provisioning and migration; do not erase volumes to work around that requirement. Keep the database, edge-artifact and demo-data volumes to retain sessions and observations.

## Operator workflow

Choose Simulation Lab, select a preset, choose L1/L2 where supported, playback 1×/2×/5×/10×, and optional inspection inclusion. Seed and immutable session dataset identity are displayed. Start creates a durable session and requests execution. Pause/Resume operate the actual publisher, and Stop ends only that session. Pending requests remain distinct from controller-acknowledged states. Restart creates a new session; it does not reset old conditions or delete evidence.

| Preset | Actual implementation / interpretation |
|---|---|
| Healthy Operation | Original healthy virtual process data; qualified monitoring and complete green are not guaranteed |
| Localized Deformation | Original geometric scenario and B3.1 processing when inspections are included; no guaranteed detection |
| Thermal Anomaly | Original thermal scenario, quantitative frames and operating analytics; image findings need not have physical asset association |
| Critical Pressure | Original severe process scenario; inspection inclusion forced off; F1 evaluates authoritative current pressure without UAV corroboration |
| Degraded Sensing | Original geometric scenario with L2 forced server-side; insufficient coverage/inconclusive results remain visible |
| Sensor Interruption | First 80 healthy IoT observations, then 16 actual wall-clock seconds without publication; no inspection delivery |

The selected configuration is immutable for a running session. Stopping playback does not clear advisories, acknowledge them or infer recovery. Historical findings can remain visible during a new healthy preset. Use the Measurements link for a session-specific stored-reading filter; clear it to inspect all history. Inspection links select the associated real processing job. Advisories retain their original cross-session F1 lifecycle.

## Read the statuses separately

- Publisher active: controller-reported emission activity with a recent heartbeat.
- Source recently active: actual accepted edge receipt, calculated by the existing source monitor.
- Platform connected: API/event-stream availability.

An IoT-only run may activate one registered source; it does not imply 3/3. After playback stops, source recency expires naturally. Stored measurements remain visible. Preparing is indeterminate until the actual dataset is loaded. Progress counts checkpointed MQTT-acknowledged **deliveries**; an inspection bundle is one delivery. Accepted observations count actual sensor rows. Completed inspection jobs indicate processing completion, not a confirmed fault. Publisher completion can precede analytics completion.

## Authorization, recovery and bounds

Viewers read scenarios/status/history. Operators/admins create and control sessions. Execution requires both `TWINGUARD_PROFILE=simulation` and `TWINGUARD_DEMO_ENABLED=1`; site-review is rejected even if the enable flag is set. No browser profile or calibration-trust setting exists. Existing source-registration trust guards remain enforced.

Only one session owns the default namespace. UUID command keys and durable records prevent duplicate Start from creating additional publishers. On unexpected controller restart, an owned interrupted session becomes failed with its last checkpoint retained; an in-flight delivery may already have committed. It is not replayed automatically. Use Restart for a fresh identity. Parent-death cleanup and bounded generation prevent orphan generators.

Defaults bound generation to 180 seconds, one child, 512 MiB dataset size, 10,000 sensor-publication records and 200 persisted sessions before administrator storage review. The optional controller is limited to 0.75 CPU, 1536 MiB and 96 PIDs. Backpressure waits when processing backlog exceeds 500; it does not rejuvenate old acquisition times. Demo datasets remain in a separate managed volume, outside frozen experimental outputs. No automatic scientific-history deletion is implemented.
