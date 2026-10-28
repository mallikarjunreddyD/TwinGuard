# Phase 5 architecture

Version 0.6.0 adds an operational layer around unchanged Phases 0–4. The pure F1 engine remains the only production hazard decision implementation. API/frontend code does not reproduce hazard rules. See PHASE5_VALIDATION.md for measured results and acceptance decisions.

## Services and paths

Mosquitto provides authenticated QoS 1 transport and exact source-topic ACLs. `edge.protocols.subscribe` receives authorized broker topics, binds the connection identity through those ACLs, and calls `edge.ingestion.ingest`. PostgreSQL stores the inbox, public observations, leased jobs, versioned records, fusion checkpoint and transactional outbox. The public-only artifact store uses content hashes rather than caller filesystem paths.

The fast worker consumes IoT jobs and invokes existing operating analytics, the configured engineering-limit adapter, and F1. A separate Open3D worker handles verified inspection bundles through the existing registration/B3.1 and thermal code. Heavy jobs cannot occupy the fast worker. Both serialize F1 transitions on the locked checkpoint row.

The existing FastAPI app exposes authenticated REST, public artifacts and resumable SSE. Nginx serves the compiled React/TypeScript application and proxies the API. Three.js loads accepted baseline GLB geometry; charts and overlays derive from stored public observations and analysis records. Original geometry remains unchanged.

The optional OPC UA simulator exposes numeric measured channels, units and public-record lineage. Its read-only adapter uses the same ingestion function, source registry and unique observation identity as MQTT. Duplicate transport representations do not create independent measurements.

## Trust and scientific boundary

The controller in `scripts/edge_demo.py` may generate synthetic observations; it runs outside deployed services. Runtime images contain core public contracts/loaders, analytics, fusion, edge code, accepted references and frozen healthy calibration models. They exclude `plant`, `sensing`, `evaluation`, scenario files, private datasets, core private configuration and registry modules. Public manifests and arrays retain existing validation gates. No evaluator labels are consumed by workers or dashboard.

Separate deployment profile configuration selects illustrative simulation or conservative site review. Profile/policy/model provenance is server controlled. Unknown physical calibration or clock synchronization cannot be repaired by a frontend selector.

## Operational limits

This is one workstation with a PostgreSQL-backed queue, not a high-availability cluster. Working evidence is bounded by policy horizons plus latest samples and unresolved-event support; full public evidence and decision history remain durable. Unresolved advisory history can continue growing and needs reviewed capacity/archival management. Application database roles are not superusers; table ownership for local migrations is broader than a production service-specific SQL privilege split. No control, actuation, RUL or Phase 6 optimization is implemented.
