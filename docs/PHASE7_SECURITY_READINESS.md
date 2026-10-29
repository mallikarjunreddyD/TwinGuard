# Phase 7 security readiness

**Feasible laboratory checks executed; industrial/site commissioning remains BLOCKED/PENDING (P5-03).** The user confirmed no physical data or equipment is available. Local loopback identities, short-lived test certificates and simulation calibration authority are not approved site trust.

| Check | Actual result | Evidence |
|---|---|---|
| Authenticated MQTT source identity/topic ACL | Wrong credential rejected; wrong-source-topic message not persisted in full E4 | Full E4 report and raw broker/API observations |
| Malformed schema/asset/unit/source/future time/nonfinite | All six quarantined | `phase7/security_checks.json` |
| API RBAC and artifact boundary | Anonymous 401, viewer operator action 403, unknown artifact 404, unsafe/private bundle 422 | Same actual API checks |
| Application DB privileges | No superuser/createdb/createrole/replication/bypass-RLS flags; server-file read and role creation rejected | `phase7/database_privilege_checks.json` |
| HTTPS TLS | CA-verified protected endpoint 200; untrusted system CA rejected | `phase7/lab_tls.json` |
| MQTT TLS | CA-verified authenticated connection succeeded | Same, separate actual lab broker |
| OPC UA | Pinned-certificate Basic256Sha256 SignAndEncrypt read succeeded with source timestamp; write rejected BadUserAccessDenied; unencrypted connection rejected | Same; actual certificate-enabled server path |
| Dependency consistency/advisories | pip check passed; OSV query returned no advisories for 118 installed locked Python packages | `phase7/python_advisory_review.json` |
| Frontend advisory correction | Initial audit had 1 moderate and 2 critical development-tool findings; upgraded Vitest to 5.0.5; tests/build passed and follow-up audit has zero findings | `phase7/npm_audit_before.json`, `phase7/npm_audit_after.json` |
| Backup/artifact integrity | Canonical SQL rows, CAS files and 5120 archived messages verified after real restore | Storage validation report |

The first laboratory TLS attempt verified HTTPS but failed broker key access; the second also verified MQTT but failed OPC UA key format inference. Both failed reports remain. A third fresh run used appropriate protected PEM key files and passed the listed protocol checks. These are two-day self-signed **LAB ONLY** certificates, not industrial certificates. Lab broker root access was used only to read the protected bind-mounted test key; it is not a recommended site configuration. Private keys/tokens remain in gitignored `.edge` files; reports contain public results and hashes, not credentials.

Default demonstration HTTP/MQTT and optional NoSecurity OPC UA remain explicitly local-lab interfaces. The secure OPC UA server path is conditional on both certificate and key; a half-configured identity fails. Certificate trust/revocation, key rotation and storage, source-clock discipline, approved process limits, instrument calibration, operator account expiry/SSO, firewall review and site authorization remain uncommissioned. A clean advisory scan is time- and scope-limited, not a proof of security; no base-image/OS vulnerability scan is claimed. Field readiness is NO-GO until attributable site prerequisites are met.

