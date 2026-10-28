# Edge ingestion

`src/twinguard/edge/contracts.py` defines SourceRegistration and EdgeEnvelope; JSON Schemas are exported under schemas/. The original SensorObservation and InspectionCapture contracts are unchanged.

A registry entry binds source/site, independent transport identity, allowed sensor/asset/type/unit mappings, configuration version, clock basis, instrument calibration reference and expected interval. Inspection sources also bind capture sensor IDs to allowed assets. Authentication, installation, calibration, validity, clock synchronization and policy approval remain different claims.

Each delivery records the actual UTC edge receipt time. Original device acquisition/receipt/clock claims remain in the public observation body; trusted edge metadata is separate. Unknown clocks remain unknown regardless of the payload's claim. Controlled simulation replay is accepted only for registered synthetic sources with an explicit replay clock basis. Physical sources cannot enable replay by changing their payload.

Inbox message keys and observation keys are enforced by SQL primary keys. Exact retransmissions produce an audit, not another job. A second transport with the same original observation is deduplicated. Conflicting identities/payloads are quarantined. Archived message identity/digest is still checked after raw-inbox archival.

Validation covers envelope schema, maximum 128 KiB telemetry, finite values and units, installation/configuration, timezone-aware ordering, publisher future/skew bounds, future acquisition, original artifact hashes, formats and public path confinement. Old valid readings remain historical/stale instead of being retimed silently. Sequence gaps/out-of-order deliveries are audited. Pending-job admission is bounded at 10,000; source delivery is not claimed lossless under unlimited overload.

Inspection upload is a two-step process: an operator uploads a bounded ZIP to POST /api/v1/inspection-imports, then an authorized source publishes its content hash on the inspection manifest topic. Upload does not itself authenticate an inspection source. Only public manifests/observations are admitted. Arrays are loaded without pickle and preserve coordinate, mask and calibration metadata. The object store uses atomic content-addressed creation and verifies hashes again before processing. No user-selected server path is accepted.

Rejected messages create bounded digest/reason audits, not scientific evidence. A committed quarantine is acknowledged at MQTT; uncommitted database failures leave transport delivery eligible for retry.

Publisher sequence epochs are explicit. A new replay dataset starts a new epoch; its counter reset is audited separately from packet reordering. Observation identity excludes transport receipt/processing/delivery flags but includes scientific value, unit, acquisition, quality and provenance. Separate delivery IDs preserve each representation. Inspection bundles bind a source-clock anchor/rate to the same telemetry replay clock; baseline and current frames never share a fabricated batch acquisition time. Repeated immutable bundles schedule only one analysis job.

Credible configured critical crossings receive a server-computed durable scheduling hint using the existing engineering-limit adapter. This only changes queue order; the worker still rechecks calibration, clocks, freshness and the bound F1 policy. Publisher payloads cannot set queue priority. Validated policies are cached by file path, nanosecond modification revision and size, so repeated parsing cannot block ingress while configuration changes still invalidate the cache.
