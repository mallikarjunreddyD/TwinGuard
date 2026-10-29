# Phase 7 validation backlog

Current Phase7 findings are recorded in the dated update below. The original handoff is preserved as historical context.

These four Phase 5 concerns remain OPEN. Phase 6 synthetic planning does not close them. Phase 7 has not been implemented.

| ID | Current status and original evidence | Required test and acceptance criteria | Assigned phase / output artifact | External dependency / actual result |
|---|---|---|---|---|
| P5-01 | OPEN. Full FIFO E4 qualified 6/186 current critical readings; focused corrected scheduler qualified 186/186 with 302 older ordinary jobs. Complete corrected mixed workload was not rerun. | Reexecute sustained mixed streaming, transport overload, restarts/recovery. Report freshness, late/missed critical readings and alert latency against unchanged temporal rules; all declared acceptance targets must be met. | Phase 7 / corrected full E4 report, raw delivery and job timestamps. | Sufficient representative edge runtime/hardware. Focused result remains evidence only for its workload; Phase 6 planning-load measurements cannot close this. |
| P5-02 | OPEN. Phase 5 extrapolated substantial full-database growth (768.90 GiB/90 days); this was not an endurance result. | Measure history growth, bounded archival, checkpoint compaction, unresolved evidence retention, indexing/query performance, backup/restore; recalculate storage from actual workloads. Require preserved lineage and unresolved advisories after restore. | Phase 7 / retention, growth, query and restore report. | Representative storage/workload and equivalent duration. No 90-day endurance result executed. |
| P5-03 | OPEN. Authenticated local MQTT/API and read-only OPC UA demonstrated; industrial deployment trust uncommissioned. | Commission TLS/certificates, calibration evidence, synchronized clocks, approved engineering limits, source/operator identity governance, deployment network review, physical integration and site approvals. Each field prerequisite must have attributable evidence. | Phase 7 / commissioning checklist and signed site evidence. | Field-only requirements PENDING/BLOCKED until hardware, approved limits and site authorization are available. No commissioning evidence fabricated. |
| P5-04 | OPEN. L2 geometric abstention, B3.1 localized_relative scope, unknown global/support displacement, thermal image-only association remain. | Test hardware measurement sensitivity, alternative viewpoints physically, thermal calibration/physical association and independent surveyed reference. Report detection/qualification with unknowns separate from negatives. | Phase 7 / physical sensing and independent metrology report. | Actual LiDAR/thermal hardware and site/metrology access. Phase 6 synthetic alternative-view evidence does not establish physical capability. |

Actual Phase 6 results and limitations are recorded in PHASE6_VALIDATION.md when execution completes. None of the items above is silently removed or marked closed by a focused benchmark.

## Additional Phase 6 research limitations

- **P6-01 — OPEN:** Validate wider-view B3.1 calibration/registration suitability on a disjoint development partition. E5 healthy-control new-view positives were 57/210 for P0/P2, 7/210 for P1 and 17/210 for P3. Do not tune the reported held-out benchmark or weaken B3.1 gates. Output: independent view-domain calibration/generalization study.
- **P6-02 — OPEN:** Build equivalent public measurement calibration for competing assets and richer independent occlusion/sufficient-coverage/reinspection scenarios. Current S01/S06/S07/S15 interpretations are limited; keep actual partial coverage distinct from complete inspection. Output: preregistered expanded E5 protocol and results.
- **P6-03 — OPEN:** Execute complete acquisition-level component ablations and longer representative planning-load tests, with terminal CPU/resource accounting and retained critical freshness. Planning-only ablations and the 30+30 replay load check do not substitute for these studies. Output: paired ablation/resource report.

These are future validation requirements only. Phase 7 has not been implemented.


## Phase 7 update — 29 October 2026 (Asia/Calcutta)

No prior issue is silently closed. See the Phase7 reports and tracked compact evidence under `docs/phase7`.

| ID | Phase7 status | Actual evidence and remaining requirement |
|---|---|---|
| P5-01 | **OPEN** | New full E4 retest completed 19 profiles / 6204 jobs / 99 concurrent plans, but only 168/186 critical readings were current; 18 stale. Measured backlog test: 116/188 current, 72 stale. Saturation rejected a real critical message. The unchanged 10s temporal boundary is not met across these workloads. |
| P5-02 | **PARTIAL, remains OPEN** | Actual bounded archival of 5120 completed inbox rows, SQL/CAS/archived-message recovery and query/index measurements passed. Full F1 trace/idle history growth and representative capacity/endurance remain unresolved. |
| P5-03 | **PARTIAL, field work BLOCKED** | Actual auth/ACL/RBAC, DB privileges, CA-verified lab HTTPS/MQTT and encrypted read-only OPC UA checks executed; dependency findings corrected and rechecked. Site-approved trust, clocks, calibration, limits and commissioning absent. |
| P5-04 | **BLOCKED / PENDING physical resources** | User confirmed no physical data or equipment. Surveyed 10/20/30/50mm target and thermal protocols are documented; no physical sensitivity result is fabricated. |
| P6-01 | **PARTIAL, remains OPEN** | 216 diagnostic pairs, 600 independent healthy calibration pairs and 1140 heldout pairs executed. B3.2 lowers healthy positives but loses substantial unconditional recall through abstention. It does not replace B3.1. |
| P6-02 | **PARTIAL, remains OPEN** | Fresh paired comparison plus separately frozen missed-view, independent-occluder and measured tiny scoped-coverage controls. Equivalent multi-asset measurement calibration remains absent; no whole-asset coverage claim. Final journals govern completion. |
| P6-03 | **PARTIAL, remains OPEN** | 180 actual acquisition ablation trials and full planning-load stress executed. Some variants select zero additional views and cannot establish component benefit; currentness and representative-resource limits remain. |

New operational findings: the first full controller's global drain deadline expired during overlapping workloads; a fresh retest with a declared larger recovery observation window completed, without changing TTL. PUBACK does not mean durable admission at queue saturation. Raw archival alone cannot bound full trace growth. These negative results are release limitations, not passed reliability targets.


## Final Phase 7 disposition

| Issue | Final status | Evidence and remaining work |
|---|---|---|
| P5-01 | OPEN | Full light E4: 186/186 current. Actual heavy overlap: 145/184 current, 39 stale. Separate original-rate replay: 43/62 current with source delay already present before emission. Bound queue/service and publisher pacing before reliability closure. |
| P5-02 | PARTIAL / OPEN | Verified SQL/CAS/raw-archive restore and 5,120 archived inbox rows; unbounded trace/checkpoint growth and 90-day endurance remain unresolved. |
| P5-03 | PARTIAL / site PENDING | Laboratory authentication, privileges and encrypted protocol checks passed; approved site trust and commissioning are absent. |
| P5-04 | BLOCKED | User confirms no physical data or equipment. Physical protocol is proposed, unexecuted. |
| P6-01 | PARTIAL | Supported-domain calibration reduces false positives, but global abstention and recall remain poor. |
| P6-02 | PARTIAL | All five planners evaluated; multi-asset calibration support remains unequal and P3v2 does not establish general superiority. |
| P6-03 | PARTIAL | Actual acquisition-level ablations completed; some components select no extra scans and their benefits remain unestablished. |

All 240 main paired cases and 90 supplemental controls completed. Extra chronology: 23/30 committed; seven remain blocked by source-host storage headroom. No issue is closed on the basis of missing physical or incomplete extra evidence.


## WSL relocation follow-up

The seven storage-blocked extra chronology cases were resumed after confirming the E: WSL backing location and restored free space. All 30/30 cases now completed. This closes the extra chronology execution gap; it does not close P5-01, physical validation, or the other research limitations above.
