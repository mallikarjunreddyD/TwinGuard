# Isolated simulation-controller architecture

Browser → authenticated FastAPI command → PostgreSQL session/command tables → isolated controller → public MQTT observations / validated public inspection bundle → existing ingestion, analytics and F1 → stored records / SSE → dashboard.

## Boundaries

The API imports public session contracts and lifecycle functions only. Its image still excludes `twinguard.plant`, `twinguard.sensing`, `twinguard.evaluation`, privileged `twinguard.demo`, and the generation CLI. No Docker socket, subprocess execution API, arbitrary Python expression, raw command, dataset path or private-world endpoint is added. The optional controller image alone includes the original simulator, sensing/evaluation-generation modules and declared scenario templates. Public export/bundle validation remains the observation boundary.

The controller reuses `scripts/edge_demo.py` generation and publication. Optional omission of unrequested inspections avoids unnecessary work; the original default CLI behavior remains available. The shared publisher now checks controls during pacing waits and emits progress after actual PUBACK. Its standard-library HTTP uploader posts only the manifest-referenced public files. Private poses, point-truth labels and world state remain solely in controller storage. Runtime API artifacts and frontend files never receive these directories.

## Persistence and idempotence

Migration `0003_demo_sessions` creates `demo_sessions` and `demo_commands`, independently of the historical scientific records. A unique nullable active-namespace column and serialized PostgreSQL command transaction reserve one publisher. Session identity derives from actor plus UUID creation key; retries return the same immutable configuration. Command keys are session-scoped and cannot be reused for another action. Invalid lifecycle transitions return conflict rather than starting work.

Lifecycle: idle → preparing → ready → running; running ↔ paused; active → stopping → stopped; finished publication → completed; errors or interrupted owned sessions → failed. Desired state records the request, while controller state acknowledges execution. Terminal updates release namespace ownership without deleting evidence. A lifetime controller advisory lock prevents two service instances from publishing concurrently. Restart recovery retains cursor/count/provenance and fails interrupted work, never silently replaying from zero.

Session storage includes actor/configuration/seed/fidelity/rate, creation/start/pause/resume/end history, position, planned and checkpointed delivery counts, last delivery timing, controller heartbeat, inspection-message reference and sanitized error. Accepted sensor counts, latest accepted observation, job states and processing backlog are derived from durable operational tables. Only public session provenance is added to transport metadata; scientific observation bodies remain unchanged.

## Clock semantics

Original scientific acquisition/receipt values remain inside public observations. Simulation mode explicitly maps acquisition to replay wall time at the selected rate. Actual emission, broker acknowledgment, edge receipt and analytics availability remain separately recorded. Pause stops publication and advances the declared replay origin by the actual paused duration; sequence/epoch and source position continue unchanged on Resume. Backpressure delay does not shift acquisition into the present. Existing F1 freshness and critical-evidence qualification are untouched.

## Deployment and trust

Use a separate lab Compose project, network, broker, PostgreSQL volume, artifact volume and managed demo-data volume. Controller credentials are separate from human operator/viewer tokens. Its database login is nonsuperuser and restricted to session SELECT/UPDATE and job SELECT; it cannot edit condition/event records. A dedicated service-principal token uploads validated public bundles. Source publishing identities remain the existing broker-ACL-bound demo sources, with explicit assumed-simulation calibration and declared replay clocks.

The default production image does not contain the privileged controller. Base deployments leave execution disabled. Site-review checks use a separate read-only test API/frontend against the isolated LAB database, not a commissioned plant. Review capability and source activity do not confer sensor-calibration trust, engineering approval or physical control authority.
