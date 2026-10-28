# Phase 7 baseline inventory

Starting branch phase-6-risk-adaptive-inspection, exact revision a283713ef6ecfb8b7f883b76701e39ec22e8e5ce, software 0.7.0. New branch phase-7-final-validation. The source, frozen models/policies, validation reports and prior numerical manifests are SHA256-indexed in baseline_manifest.json before candidate algorithm changes.

| Evidence category | Existing result | Qualification |
|---|---|---|
| Demonstrated software | Seven-asset simulation, original imperfect sensing, B3.1/thermal/operating analytics, F1, authenticated protocols, PostgreSQL, P0–P3 and real dashboard | Synthetic/loopback research evidence; not commissioned equipment |
| Existing experimental failure | E5 new-scan localized detections P0/P2 165/240, P1 115/240, P3 117/240; healthy-control positives 57/210, 7/210, 57/210, 17/210 | Historical definitions and files retained; no result replacement |
| Reproducible negative result | Zero additional discoveries for every E5 strategy; 30 actual alternate-view L2 probes yielded zero qualified patches | View changes do not establish improved precision |
| Operational unresolved | Complete corrected E4 not repeated; storage growth/retention/backup/restore not fully characterized | P5-01 and P5-02 remain OPEN before new measurements |
| Unverified field capabilities | TLS commissioning, hardware source identity/calibration/clock trust, site limits, flight/site approval | P5-03 OPEN; site-only requirements PENDING/BLOCKED |
| Physical capability | No documented LiDAR/thermal hardware or surveyed physical measurement cohort available in connected repository manifests | P5-04 remains OPEN; physical test execution BLOCKED pending equipment/data |
| Independent external-data validation | Dataset manifests inspected; no independently measured licensed cohort currently demonstrated | PENDING, not replaced with synthetic data |
| Reproduction scope | Prior source/models and machine-readable metrics are available; physical/industrial claims have no independent reproduction evidence | New targeted experiments will not masquerade as a full historical reproduction |

Phase 7 baseline reproduced: 307 pytest tests passed; Ruff passed; Mypy checked 107 files; production frontend build and all three frontend tests passed. Exact logs are in phase7/baseline_software_checks.json. A real host filesystem failure interrupted the first Phase 6 campaign. Linux free space alone is insufficient: host C: has approximately 22 GiB free at entry. New runs must reserve host space, bound workers and checkpoint completed cases. Earlier incomplete outputs remain incomplete and are not deleted or counted successful.

All four P5 issues and three P6 issues begin OPEN. No closure is authorized by a report alone. Read PHASE7_VALIDATION_BACKLOG.md for original requirements.
