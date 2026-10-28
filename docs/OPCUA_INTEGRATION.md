# Read-only OPC UA integration

`python -m twinguard.edge.protocols opcua-server --bundle /measurements --endpoint opc.tcp://0.0.0.0:4840/twinguard/` exposes only public SensorObservation values. Numeric nodes include pressure, process/surface temperature, operating load and phenomenological vibration channels from the original sensing layer.

Namespace URI: `urn:twinguard:measured`. Resolve its namespace index dynamically. String node identifiers are installed sensor IDs, for example `pressure-01`. Companion `<sensor>.Unit` gives engineering units and `<sensor>.Record` preserves the complete original observation identity/quality/provenance. Nodes are read-only for clients. The simulator writes its own measured values; this is not plant actuation.

`python -m twinguard.edge.protocols opcua-client --endpoint ...` reads configured source nodes, numeric types, units, OPC UA status and source/server timestamps. Non-atomic numeric/record companion updates are retried rather than combined. Bad statuses invalidate measurements. Original observations share their identities with MQTT, preserving deduplication/dependence. Polling snapshots are supported; this implementation does not claim every server update is captured by a historian subscription.

The adapter reconnects after endpoint failure and audits disconnects. It forwards through the same authenticated registry/validation function used by MQTT. A service identity (`opcua-adapter`) binds the optional `opcua-demo` registration; it is not taken from payload JSON.

The optional Compose `demo-opcua` profile uses an internal NoSecurity laboratory server. The client refuses that mode unless TWINGUARD_OPCUA_LAB=1 is explicitly configured. Prospective secure channels use TWINGUARD_OPCUA_SECURITY with asyncua's security string containing the approved client certificate/key and pinned server certificate. These credentials must be externally provisioned/mounted. Physical server address-space mappings, certificate issuance/rotation and verified instrument/clock approval require site commissioning. Arbitrary industrial OPC UA address spaces are not auto-discovered into trusted measurements.

The deployment contains no OPC UA write/control client or plant method invocation.
