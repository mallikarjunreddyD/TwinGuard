# MQTT protocol

The demonstrator uses the real Eclipse Mosquitto 2 broker and paho-mqtt 2.1.0. QoS 1 is at-least-once transport; duplicates are expected. SQL constraints and transactional processing provide idempotent observable effects under the documented lease/commit assumptions, not exactly-once communication.

Topics:

- `twinguard/v1/plant-01/iot/demo-iot/observations`
- `twinguard/v1/plant-01/inspection/demo-uav/manifests`

Each source has its own generated non-default credential and exact publish ACL. The ingestion service has a separate subscribe-only identity. MQTT does not expose a publisher username to ordinary subscribers; the adapter establishes source identity from the broker-enforced topic/username ACL, then checks payload source/site and sensor mapping. This relies on the reviewed broker ACL being part of the trusted boundary. Payload identity alone is insufficient.

EdgeEnvelope carries schema version, stable message/source ID, kind, sequence, actual emission time, configuration/provenance references, original observation or immutable bundle hash, and an explicit live/replay mode. Raw records preserve original sensor/asset/type/unit/acquisition/quality fields.

The clients use persistent sessions, bounded 10,000-message queues, reconnect backoff and explicit PUBACK waits. The ingestion client manually acknowledges after durable acceptance/quarantine. A broker outage can buffer messages in the running publisher's memory, but publisher-process crash-safe offline spooling is not implemented. PUBACK confirms broker handling, not database persistence; E4 compares publisher IDs with durable observations.

The default broker is on the internal Compose network, not publicly exposed. Validation alone binds 127.0.0.1:18783. Laboratory credentials travel without TLS on that isolated local path. For non-loopback use externally issued certificates and `deployment/edge/mosquitto-tls.conf.example`; use authenticated registered usernames inside TLS and review ACLs. TLS examples are configuration templates, not production certification or a tested campus deployment claim.
