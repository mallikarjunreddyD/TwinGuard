# Phase7 final validation

**CONDITIONAL GO — software research demonstrator operates, with material generalization, multi-asset, long-horizon capacity and representative-environment validation limits. Physical/industrial readiness: NO-GO / BLOCKED.** User confirms no physical data/equipment. This is a truthful software-validation package with explicitly reported incomplete extra work, not an industrial certification.

Starting revision `a283713ef6ecfb8b7f883b76701e39ec22e8e5ce`, branch `phase-7-final-validation`, software 0.8.0. Scientific freeze `edae1e5`; tested operational correction `a35c790` with exact running-image source hashes. Final source/package revisions are recorded separately.

## Acceptance gates

| Gate | Status | Evidence / limit |
|---|---|---|
| G1 | PASS | Historical E1–E5 and empirical reports/models/policy retained; baseline307tests and manifest |
| G2 | PARTIAL / scoped correction | Independent healthy calibration and1140pairs; same supported domains improve FP with small sensitivity loss; global abstention/recall tradeoff unresolved |
| G3 | PASS evaluation; benefit limited | All five methods under both common detectors; full paired outcomes, true-missed controls and real ablations; no unsupported superiority |
| G4 | PASS | Scientific candidate files/model unchanged from freeze; no private/future observations in production; infrastructure-only recoveries recorded |
| G5 | PARTIAL — heavy mixed timeliness fails | Light full workload186/186current; actual heavy mixed workload145/184current,39stale; admission/restarts and failure boundary retained |
| G6 | PASS recovery / PARTIAL capacity | Actual archival, SQL/CAS/raw restore, queries/index growth; no90-day endurance |
| G7 | PASS feasible lab / PENDING site | Auth/ACL/RBAC/privileges, actual lab TLS and readonly encrypted OPC UA, advisory fixes; site trust uncommissioned |
| G8 | BLOCKED physical | User confirms no equipment/data; surveyed physical protocol and blockers recorded |
| G9 | PASS software scope | Actual reviewed acquisition/F1/replan, duplicate/restart and real-data browser evidence |
| G10 | PASS typed evidence | Per-capability hashes/versions/provenance/repro commands; raw/registered point audits; negative outcomes retained |
| G11 | PASS | 336pytest, Ruff/format/Mypy114, frontend3tests/build/audit and live browser/Docker checks |
| G12 | PASS conservative assessment | Software laboratory TRL4-consistent scope; industrial5/6 not established, physical/siteNO-GO |

## Executive outcome

B3.2 reduces healthy positives on identical supported cases (18/60→4/60; localized faults237/240→235/240), but globally detects235/840 versus635/840 for B3.1 and abstains840/1140. B3.1 remains default. P3v2 is an explicit engineering utility, not a detection probability; full comparisons, unknowns, qualified areas and measured resource limits are reported separately.

The final full E4 observed186/186current critical readings; earlier full168/186 and backlog116/188 are preserved. The admission correction passed the10000/10100pending boundary, and the corrected heavy/critical overlap test is independently timestamp-checked. The 10-second TTL is unchanged. Storage restore/archival and lab security passed their scopes; trace growth, physical metrology and site trust remain open.

## Reports and reproduction

- [Baseline inventory](PHASE7_BASELINE_INVENTORY.md), [exact freeze](phase7/CANDIDATE_FREEZE.json), [evidence register](phase7/EVIDENCE_REGISTER.md).
- [Geometric diagnosis](PHASE7_GEOMETRIC_GENERALIZATION.md), [planner corrections](PHASE7_PLANNER_CORRECTIONS.md), [independent paired results](PHASE7_INDEPENDENT_VALIDATION.md).
- [Full E4 and bounds](PHASE7_E4_CORRECTED_STRESS.md), [storage](PHASE7_STORAGE_VALIDATION.md), [security](PHASE7_SECURITY_READINESS.md).
- [Integrated demonstration/screenshots](PHASE7_INTEGRATED_DEMONSTRATION.md), [physical protocol](PHASE7_PHYSICAL_VALIDATION_PROTOCOL.md), [TRL assessment](PHASE7_TRL_ASSESSMENT.md), [P5/P6 issue register](PHASE7_VALIDATION_BACKLOG.md).

External evidence lives at `D:\TwinGuard` (`/mnt/d/TwinGuard`); the original157-case pre-migration copy remains retained. Migration verified46207files before resuming and records resource-only source drift. Supplemental allocation failures and a recycled-executor stall were preserved and recovered sequentially using one case per fresh process. Original main stale_initial is a delayed-data control; the separately declared chronology study genuinely acquires later without retiming measurements; see its explicit committed/expected count and any source-drive blocker. Mission durations are static proxies; per-method controller CPU/wall includes shared cache overhead and is not proof of algorithm runtime superiority.

Use the versioned `scripts/phase7_*` controllers with new output directories and explicit loopback compose overlays. `phase7_summarize.py`, `phase7_view_metrics.py`, `phase7_evidence_register.py` and `phase7_finalize.py` derive checked reports from preserved journals; none marks unexecuted trials successful. The new private certificates/secrets stay gitignored. Physical and site-only gates require the documented resources and independent authority before deployment.


Execution counts:240/240main paired cases,90/90supplemental controls,180/180actual-acquisition ablation trials and1140/1140detector pairs. Extra chronology:30/30committed; remaining cases are not claimed successful.


## Completed after WSL relocation

The user migrated Ubuntu-24.04 to `E:\WSL\Ubuntu-24.04`. Registration and storage were checked before resuming. All seven pending chronology cases completed under unchanged scientific configuration, bringing the additional study to 30/30. Earlier 23/30 reports describe the prior storage-blocked state; no missing trials remain in this study. The 240 main cases, 90 supplemental controls and 180 acquisition ablations were preserved without rerunning.

The requested original-rate replay remains 43/62 current because samples were delayed before emission; publisher lag p95 was 10.748 seconds and post-ingestion queue p95 was 0.339 seconds. This does not establish a 1 Hz server-capacity failure. Heavy mixed timing and physical/site validation remain open.
