# Proposal claim traceability

All numerical claims concern synthetic experiments or laboratory software integration. Git references identify scientific freezes or preserved producer metadata; the release packaging SHA is not substituted for an unknown producer SHA.

| ID | Exact claim | Source report | Machine-readable artifact / experiment | Revision | Evidence type | Limitations; proposal use |
|---|---|---|---|---|---|---|
| C1 | Integrated virtual sensing, analytics, fusion, protocols, dashboard and planning implemented | PHASE7_INTEGRATED_DEMONSTRATION.md | phase7/integrated_reinspection.json; integrated_browser_recovery.json | a35c790 operational; 5b9390a final UI | Actual software with virtual inputs | Laboratory scope; appropriate |
| C2 | B3.1 localized 635/840 faults; 27/300 healthy positives | PHASE7_INDEPENDENT_VALIDATION.md | phase7/heldout_detector_summary.json; V3 held-out detectors | edae1e5 freeze | Independent synthetic scan pairs | 75.6% unconditional recall on this distribution; appropriate |
| C3 | B3.2 localized 235/840; 4/300 healthy positives; 840/1140 inconclusive | PHASE7_INDEPENDENT_VALIDATION.md | phase7/heldout_detector_summary.json | edae1e5 | Independent synthetic scan pairs | Reduced false positives with high abstention; no promotion; appropriate |
| C4 | Supported common cases: healthy positives 18/60→4/60; localized detections 237/240→235/240 | PHASE7_INDEPENDENT_VALIDATION.md | phase7/heldout_detector_summary.json common applicability subset | edae1e5 | Conditional synthetic subset | Conditional applicability, not global performance; appropriate |
| C5 | E2 load-transition operating FPR 81.3%→0%, 1% abstention | PHASE3_VALIDATION.md | phase3_e2_results.json; phase3-full/E2/report.json | Producer metadata in original E2 configuration/seals; packaging abf5d8d preserves report | Synthetic E2, 30 sequences | Five seeds per condition; correlated samples; appropriate |
| C6 | Thermal transition FPR 20/25→0/25 with 8% inconclusive; 15/15 hotspot frames; mean IoU 0.439 | PHASE3_VALIDATION.md | phase3_e2_results.json | As C5; no invented producer SHA | Synthetic thermal E2 | Scope and spatial-association limitations retained; appropriate |
| C7 | E3-B F0 recall 32/330; F1 recall 270/330 and precision 83.08% | PHASE4_VALIDATION.md | phase4/results.json; phase4/final_revision.json | 42965802943ef44c94d434c7ca3d278789b66e04 | Synthetic upstream analytics and strict event matching | Principal-event/severity semantics; not physical safety reliability; appropriate |
| C8 | Final lighter E4 186/186 current; heavy mixed 145/184 current and 39 stale | PHASE7_E4_CORRECTED_STRESS.md | phase7/V4-full-E4-admission-retest-summary.json; V4-mixed-boundary-retest-v3-summary.json | a35c790 correction plus 5b9390a publisher; source hashes retained | Actual local services with virtual source values | Heavy-load freshness FAIL retained; appropriate |
| C9 | 5,120 inbox rows archived; SQL/artifact recovery verified | PHASE7_STORAGE_VALIDATION.md | phase7/archive_validation.json; archive_recovery.json; storage_recovery.json | a35c790 | Executed storage/recovery | Bounded test, not long-duration endurance; appropriate |
| C10 | E5 qualified area P0 0.7344 m², P3 0.8208 m²; no additional overall discovery | PHASE6_VALIDATION.md | phase6/results.json; phase6/final_revision.json | 1779975559fdf363d134570b83a32f197517a5b4 | Synthetic paired E5 | Coverage and discovery distinct; appropriate |
| C11 | Common B3.2: P3v2 23/120 localized with 148 views; P3 31/120 with 360; P0 85/120 with 360 | PHASE7_INDEPENDENT_VALIDATION.md | phase7/heldout_planner_summary.json | edae1e5 | Paired synthetic Phase 7 | Mixed benefit; no universal superiority; appropriate |
| C12 | 240 main cases, 90 supplemental controls, 180 ablations, 30 chronology controls complete | PHASE7_FINAL_VALIDATION.md | phase7/acceptance_gates.json; supplemental_control_summary.json; acquisition_ablation_summary.json; fresh_chronology_summary.json | abf5d8d packaging; edae1e5 scientific freeze | Executed synthetic studies | Execution completion is not a positive research result; appropriate |
| C13 | Conservative laboratory software TRL 4 positioning; physical TRL 6 not established | PHASE7_TRL_ASSESSMENT.md | phase7/evidence_register.json physical/relevant-environment records | abf5d8d | Internal scope assessment | Not independent certification; appropriate |
| C14 | Equipment categories and seven milestones are proposed | PHASE7_PHYSICAL_VALIDATION_PROTOCOL.md | User-confirmed no physical equipment/data; no physical results | abf5d8d | Proposed future work | Not completed achievements or procurement commitments; appropriate |

All artifact paths above are relative to `docs/` unless explicitly an experimental run path. Claims C5/C6 retain an explicit producer-revision limitation; their committed result artifacts and archived per-case seals provide stronger attribution than inventing a historical SHA. No claim of explosion prediction, industrial safety certification, or achieved physical TRL 6 is supported or included.

## Figure captions

- `docs/ARCHITECTURE.md`: conceptual processing and evaluator-boundary diagram; not a physical installation drawing.
- `docs/phase7/figures/actual_dashboard_with_values.png`: executed dashboard rendering of stored virtual measurements; software functionality only.
- `docs/phase7/figures/detector_tradeoff.png`: independent synthetic held-out false-positive, recall and inconclusive tradeoff; B3.2 abstention remains visible.
- `docs/figures/phase3_E2_comparison.png`: original E2 synthetic analytics comparison; not a physical thermal calibration.
- Original E3 and E5 result figures should retain their original report captions and experimental populations; do not combine their populations with Phase 7.
