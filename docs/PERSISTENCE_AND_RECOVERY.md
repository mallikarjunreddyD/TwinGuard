# Persistence and recovery

PostgreSQL 17 stores operational state in a named volume. Alembic revision 0001_edge creates explicit tables: inbox, observations, jobs, versioned records and an ordered stream/outbox. Large measured arrays/GLB/PLY remain controlled artifacts, not SQL blobs. Public observation rows preserve original scientific records plus independent edge metadata.

Ingestion commits inbox, validated observation, pending job, audit and outbox together. Source-row locks serialize source identity/sequence checks. Observation/message SQL keys make repeated deliveries idempotent. Conflicting payloads are quarantined, including identities archived by retention.

Workers claim pending or expired jobs using row locks and SKIP LOCKED. Fast jobs lease for 15 seconds by default; heavy jobs lease for 120 seconds. TWINGUARD_JOB_LEASE_S overrides this. Attempts are bounded at three. A crash can repeat analytics computation, but ownership checks and one transaction protect checkpoint, assessments, events, notices, analysis, job completion and outbox effects. Expired exhausted jobs become failed. Idempotency concerns observable effects, not a claim that computation/communication happens once.

F1 transitions lock the durable checkpoint. Policy hash/method binding is unchanged; changing profiles/policies requires an explicit new/reviewed reassessment namespace, not silently loading an incompatible checkpoint. Operator actions have stable IDs and authenticated actor audits. Acknowledge is not resolve.

Evidence rows keep complete scientific history. The active checkpoint retains policy time horizons, latest stream samples and all unresolved-event positive/recovery references. This bounds expired unreferenced working data without dropping active support. State, histories and advisory notices survive process/API/database restarts. Losing the PostgreSQL/artifact volumes is outside that guarantee; deploy independent backups before physical use.

`configs/edge/retention.json` specifies the nominal 90-day objective. `twinguard.edge.storage.retain(db, days=90, limit=1000)` performs bounded raw-inbox archival while preserving identity/digest. Scientific observations, referenced artifacts, audit/action records and unresolved advisory history are conservatively retained. Complete automated scientific-history deletion/compaction is not enabled. Capacity projections use measured E4 sizes/rates; no 90-day endurance is claimed.

Runtime migrations use a non-superuser local application owner; PostgreSQL initialization uses a separately generated administrator secret. Production deployments should further split migration, ingestion, API and worker SQL grants. The default local database has no public port; validation binds loopback only.

Registered measured NPZ outputs are persisted by content hash, exposed through the authenticated artifact route and referenced by the stored registration record. Database/artifact commit ordering can leave an unreferenced object after a crash, but never publishes a metadata reference before the object exists. Backend SQL engines reuse a bounded connection pool; the snapshot endpoint reads current asset conditions and active events in one statement.

Within the fast queue, credible configured critical crossings precede ordinary jobs; legacy jobs without a hint retain ordinary priority. Pending/expired claims still use row locks and the same retry limits. Expired processing leases after the retry limit become failed, with an audit record, rather than remaining stuck indefinitely.
