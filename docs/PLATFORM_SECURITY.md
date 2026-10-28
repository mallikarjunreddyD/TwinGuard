# Platform security

This is an authenticated local research demonstrator, not an industrial security certification.

Run scripts/edge_init.py to generate unique secrets under ignored .edge/. Its directory is owner-only; secret JSON/env files are owner-readable only. Broker password hashes and API token hashes are mounted read-only. Credentials, private keys and certificates are never committed or copied into build contexts. Browser bearer tokens are held in sessionStorage, not URLs or SSE query tokens.

Roles: viewer queries; operator queries/acknowledges/uploads public bundles; administrator additionally manages unverified source registrations. Verified calibration and synchronized clocks cannot be granted by the browser source endpoint. Policy edits are not exposed. Stable action IDs prevent repeated acknowledgments, and every action records authenticated actor, target, rationale and time. Only acknowledge is available through the operator UI; repair/resolution remain reviewed Phase 4 actions outside this minimal demonstrator.

MQTT sources have separate generated identities and exact topic ACLs; ingestion subscribes separately. The OPC UA client reads only. SQL application credentials are not superusers. Internal workers/database/broker are not exposed in the primary stack. API and heavy workers run as an unprivileged UID; one-shot migration prepares the owned data volume. Containers have bounded memory. Nginx bounds upload size/rate and applies anti-sniff/frame headers.

Artifact keys are SHA256, never server paths. ZIP paths, symlinks, public scope, file types, expansion sizes, capture hashes and original array validation are enforced. APIs require authentication for model and artifact access; there is no private evaluator download endpoint. Runtime images exclude restricted generation/evaluation code and datasets.

The default HTTP/MQTT/OPC UA paths are loopback/internal laboratory transport. Prospective LAN templates are nginx-tls.conf.example, mosquitto-tls.conf.example and compose.lan.yaml.example, with pinned-certificate OPC UA client configuration. Externally issued certificates, firewall review, access lifecycle, verified clock/instrument evidence and site-approved limits remain deployment prerequisites. LAN TLS templates are not represented as experimentally commissioned production security.

A static local bearer-token map does not provide enterprise SSO, token expiry/rotation, user-specific attribution beyond configured actors, or a complete hostile-network defense. Database table ownership for migration and shared application-role credentials need further privilege separation for production. No control/actuation endpoint exists.
