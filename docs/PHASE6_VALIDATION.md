# Phase 6 validation — risk-adaptive inspection research

Executed 2026-10-28 (Asia/Calcutta), software 0.7.0, schema 1.0.0. Branch phase-6-risk-adaptive-inspection. Starting Phase 5 commit 5ed9f031a58ad7f36a498c064d1359a0a2815082; frozen planner candidate 1779975. Overall status: **PARTIAL research validation**. The engine and platform operate, but targeted fault-discovery superiority is not supported and several scenario interpretations remain limited. No Phase 7 implementation or physical UAV operation occurred.

## A. Architecture

The inspection package implements validated public planning contracts, monitoring/history adapters, accepted-reference area cells, first-hit visibility, deterministic poses, suitability/feasibility, normalized priorities, utility, constrained P0–P3, bounded exact coverage reference, explanations and causal replanning. The existing sensing, analytics, fusion and plant source files are unchanged. The edge extension adds a dedicated leased planning worker, bounded admission, immutable artifact references, authenticated request/review/result APIs, migration index and React/Three.js planning view. Module and numerical guides are linked from PHASE6_ARCHITECTURE.md.

Initial regression: 266 tests passed before implementation. Final regression: **307 tests passed**, one existing Starlette/httpx deprecation warning. Tests include actual known-plane area, first-hit occlusion, sensor frame/angular sampling, geometric/no-go constraints, constrained optimization, unknown/stale evidence, retry recovery, authorization and completed-vs-proposed-view lineage.

## B. Viewpoint and coverage model

Seven accepted assets remain unchanged. The usual complete pool contains 252 candidates: seven assets × two modalities × 18 deterministic shell positions. Only supported candidates survive modality-specific constraints; calibration is primarily available for BW-01 geometry. The accepted reference has 2,561 area-weighted cells from triangle-centroid quadrature in 80 mm voxels. Duplicate cells count once. Nominal geometric visibility, predicted measurement suitability, actual public-cloud association and qualified analytic coverage remain separate.

Real L1 angular sampling is 16 channels × 720 horizontal samples; spacing scales with range/incidence. Actual public observations are associated within 60 mm; qualification additionally requires existing valid registration and valid calibrated B3.1 patch support. This discrete area approximation does not certify every continuous surface point. Safety margins and sampled straight-segment corridors use accepted static geometry only; unknown/dynamic geometry and physical flight clearance remain unvalidated.

## C. Optimization

Priority weights and the bounded engineering utility are explicitly defined in INSPECTION_PLANNING_MODEL.md and UTILITY_AND_OPTIMIZATION.md. They are not failure probabilities or Bayesian information gain. Greedy marginal selection updates cumulative coverage, position, budgets, overlap and per-asset counts; all proposals retain review requirements. P0 is fixed order, P1 marginal coverage, P2 severity/criticality order, and P3 risk/evidence/suitability/cost utility. Identical pools and budgets were verified in every primary paired trial.

E5-A's bounded six-candidate/two-view reference achieved 4.0017096826 m² for both coverage greedy and exhaustive search (zero measured gap on this small case). This is a coverage objective, not proof of globally optimal P3 utility. Controlled complete recent coverage correctly produces continue_monitoring. Unknown maps produce requires_route_review; infeasible configurations produce no_viable_viewpoint.

## D. Closed-loop demonstration

A stored backend plan selected view-c803377db5639455ec0c9bea. The separate controller froze the plan, used its requested pose in original imperfect L1 acquisition, exported public observations, uploaded the verified bundle and published an authenticated MQTT manifest. The existing inspection worker produced **valid B3.1 / one localized region**, persisted one measured coverage record and original F1 results. A reviewed simulation-result link binds the selected pose hash, completed inspection job and plan. The next backend plan used the newly available public coverage. The existing F1 red advisory remained **red**.

Exact IDs and artifacts are in phase6/closed_loop_platform.json and experiments/outputs/phase6-platform-reinspection. Requested sensor pose, controller-private actual pose and noisy public reported pose remain distinct. Operator-local is a software-test principal; its API approval is not evidence of human site commissioning or flight permission. There is no acquisition/flight/process-control endpoint.

## E. E5 held-out results

The recovered complete run contains **18 scenario classes × 30 independent held-out seeds = 540 paired trials / 2,160 method runs**. Seeds 11100–11129 are disjoint from development 9100–9102 and diagnostic 10100. Weights, candidate rules and original sensing/detector models were frozen before held-out execution and were not retuned. Four bounded independent trial processes were used. Repeated scenario conditions and viewpoints from the same seed are correlated; comparisons bootstrap at the 30-seed cluster level.

Every per-method public plan/result seal was verified before the report evaluator read its restricted labels. All paired snapshot/candidate/budget checks, planned-before-acquisition file ordering, view/time budget checks and critical-review requirements passed. Integrity records are in phase6/integrity_checks.json. An earlier run was interrupted when the host filesystem entered emergency read-only mode; all interrupted directories were preserved and the complete recovered run used a new directory.

Primary detection requires a valid analytic region containing a valid significant calibrated patch center inside the true fault ellipse. Original broad bounding-box-overlap results are retained in raw trial rows but are not the primary localized detection metric below. Initial detections and additional discoveries are separately counted.

| Method | Acquired views | Mean new qualified area m²/trial | New-scan localized detection | Additional discoveries | Healthy-control positive trials | Optimizer p95 s |
|---|---:|---:|---:|---:|---:|---:|
| P0 | 690 | 0.7344 | 165/240 | 0 | 57/210 | 0.0948 |
| P1 | 690 | 0.8165 | 115/240 | 0 | 7/210 | 0.0675 |
| P2 | 690 | 0.7344 | 165/240 | 0 | 57/210 | 0.1027 |
| P3 | 690 | 0.8208 | 117/240 | 0 | 17/210 | 0.0772 |

Every method had 240 geometric-positive cases and the same initial **180/240** localized detections. Cumulative detection remained **180/240** for every method; **60 faults remained missed**. No method added a previously missed localized fault. New-scan confirmation recall can be lower than cumulative recall because a latched prior finding persists when a later acquisition is inconclusive. P0 and P2 coincide numerically because the feasible geometric measurements are concentrated on the same calibrated asset; this is a real calibration/pool limitation.

P3 gained 0.08642 m² mean new qualified area over P0 (95% paired-seed bootstrap interval 0.06694–0.10701 m²). Mean qualified area per estimated mission-second was 0.06173 m²/s for P3 versus 0.05176 for P0. P3's area advantage over P1 was only 0.00435 m², with an interval spanning zero (−0.00704–0.01676 m²). P3 new-scan localized recall was 48.75%, versus 68.75% for P0/P2 and 47.92% for P1. Greater area did **not** imply better discovery.

The 210 healthy-control denominator excludes thermal/process scenarios that could contain incompletely annotated secondary effects. Additional geometric positives in those other scenarios are retained separately, rather than all being called physically false. The healthy-control rates above expose a significant wider-view calibration/generalization issue; original Phase 3.1 calibration/thresholds were not altered to conceal it.

**Hypotheses:** H1 receives limited synthetic support for coverage efficiency versus P0. H2 is not supported versus P0: P3 ended with 125/540 inconclusive geometric states versus 74/540 for P0 (P1 131/540). H3 is not supported: additional discoveries were zero and new-scan recall was lower than P0. H4 is not established: all methods acquired 690 views; area/cost differences do not independently prove less redundant flight. H5 is supported for the configured synthetic L2 limitation and explicit abstention, not physical instrumentation. H6 passed all tested review/access checks.

Planning-only post-freeze ablations use the same 30 S03 public snapshots and candidate pools (210 records including the static/adaptive sequence comparison). They remove individual utility/history terms while preserving hard safety/qualification gates. Actual acquisitions were not rerun for all ablations; expected-score changes are not presented as causal detection improvements.

## F. Small deformation and L2

| Peak mm | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| 10 | 44/64 | 28/64 | 44/64 | 30/64 |
| 20 | 44/64 | 32/64 | 44/64 | 32/64 |
| 30 | 38/56 | 27/56 | 38/56 | 27/56 |
| 50 | 39/56 | 28/56 | 39/56 | 28/56 |

These denominators span paired scenario conditions, not that many independent seeds per amplitude. No hardware millimeter capability is inferred. B3.1 still estimates localized_relative changes; global/support displacement is not established. Range precision, patch qualification and registration/calibration support remain measurement limits.

A separate diagnostic froze explicitly **rejected** alternate L2 poses and acquired **30 actual additional imperfect scans**. All 30 remained insufficient_coverage, with **zero qualified patches and zero positive geometric evidence**, despite thousands of valid returns. These probes were never represented as feasible selected missions. Their public observations, unchanged B3.1/F1 results and seals are in experiments/outputs/phase6-L2-probes; phase6/L2_probes.json and Figure E5-9 summarize actual results. Changing the viewpoint did not fix L2 noise.

## G. Dashboard and platform persistence

The isolated validation deployment runs at http://localhost:18880. The earlier Phase 5 stack/data remains separate on 18780. Tokens remain local in the gitignored .edge/secrets.json; none is embedded in URLs or artifacts. The actual browser shows priorities, selected/rejected pose markers, backend FOV glyphs, predicted violet cells, qualified green measured cells, budgets, explanations, historical plans, reviews and completed synthetic-result links. It never presents predicted coverage as a measured scan.

Anonymous access was rejected; viewer creation/review was rejected; conflicting duplicate requests were rejected. Identical requests retained the same durable input hash. PostgreSQL advisory serialization protects admission and same-ID idempotence without acquiring the F1 lock. Expired leases retry; exhausted jobs become visibly failed. Only completed linked inspections count as attempted acquisitions. Plan artifacts and large cell geometry use immutable content hashes. No physical UAV endpoint exists.

## H. Performance, storage and limits

The short actual MQTT/PostgreSQL test scheduled 30 replay cases without planning and 30 during a bounded planning workload, reusing one recorded synthetic critical-pressure measurement with explicit synthetic test IDs. These are delivery/processing cases, not 60 independent sensor acquisitions. Both retained **30/30 current / 30/30 red**. Receipt-to-commit p50/p95/max was **0.090/0.149/0.190 s** without planning and **0.151/0.618/0.995 s** with planning. Ten planning requests completed during/after the loaded phase, with no load errors and no pending jobs at the endpoint. Planning imposes measurable overhead; this short workstation result does not close P5-01 or establish sustained industrial-edge capacity.

Optimizer time is separate from candidate generation/raycasting and full worker time. P3 optimizer mean/p95 was 0.04189/0.07715 s in E5. Phase6/platform_validation.json includes actual complete planning-job durations. The same short test grew PostgreSQL from 8,607,411 to 10,925,747 bytes, including observations, assessments, requests, plans and audits; this is not planner-only or long-term retention growth. Full E5 archives occupy approximately 12 GiB including privileged controller diagnostics. Public acquisition bytes per method are reported in phase6/results.json; repeated paired acquisitions are not independent data.

OS process observations record cumulative user/system CPU and observed peak RSS per E5 process (about 696 MiB peak per trial process). Monitoring began partway through execution, so terminal samples are observed lower bounds rather than exact final CPU accounting. Last observed cumulative worker CPU totaled 3011.37 CPU-seconds across the four trial processes; this includes shared trial setup and is a lower bound at the last samples. Raw container samples are preserved. Estimated mission duration/travel are geometry proxies, not battery/flight validation. All four Phase 5 concerns remain OPEN.

## I. Software and live checks

307 pytest tests passed, Mypy checked 107 source files, Ruff and formatting passed, production frontend build passed and three frontend semantic tests passed. Actual Chromium rendered the planning view with zero JavaScript errors and zero external requests. Real PostgreSQL migrations, authenticated MQTT ingestion, critical pressure processing, planning jobs, result binding and replanning were exercised. Versioned records and software logs are in phase6/.

## J. Scientific integrity and scenario limitations

Production inspection modules import neither plant, sensing implementation, evaluator nor private scenario readers. Only the separate controller generates physical scenes; only post-seal evaluation reads labels. Accepted nominal mesh geometry is a public prior, not a noiseless current fault mesh. No thresholds, sensor distributions, fault locations or held-out weights were changed after viewing results.

The complete corpus executes every declared scenario ID, but it does not establish every intended interpretation. The acquisition protocol and 30-seed matching were not changed after reading the primary results. S01's real scans provide partial qualified coverage rather than sufficient coverage of the entire plant; unnecessary-inspection behavior under complete coverage is established only in controlled E5-A tests. S06 combines partial FOV with existing geometry/self-occlusion rather than a separately injected unknown obstacle. S07's other assets lack equivalent B3.1 calibration, limiting fair multi-asset utility comparisons. S15 uses L2 abstention; the additional rejected-view probes test acquisition failure separately. Missing metadata and image-only thermal associations remain explicit. These limitations are why overall research validation remains PARTIAL.

## K. Outstanding issues

P5-01 full corrected mixed E4, P5-02 storage/retention, P5-03 industrial security/hardware trust and P5-04 physical sensing/detection are all OPEN in PHASE7_VALIDATION_BACKLOG.md. Additional Phase 6 concerns are wider-view calibration/false positives, representative multi-asset/occlusion/sufficient-coverage scenarios, and complete acquisition ablations. None is silently closed by this benchmark.

## L. Phase 7 readiness

**CONDITIONAL GO for controlled validation research; NO-GO for a superiority claim, physical UAV operation or industrial deployment.** The implemented software and reproducible negative/mixed evidence are suitable inputs for subsequent validation. Phase 7 must address calibration generalization and scenario coverage alongside P5-01–P5-04. Phase 7 was not automatically started.

## Acceptance decisions

PASS refers to the explicit tested software scope, never physical certification. Two criteria remain PARTIAL; all limitations above remain part of the result.

| Criterion | Status | Evidence / qualification |
|---:|---|---|
| 1 | PASS | Executable planning package |
| 2 | PASS | Phase 0–5 regressions preserved |
| 3 | PASS | Public monitoring snapshot adapter |
| 4 | PASS | Explainable asset priorities |
| 5 | PASS | Accepted-geometry candidate generation |
| 6 | PASS | First-hit visibility and occlusion |
| 7 | PASS | Area-weighted public-data coverage |
| 8 | PASS | Visibility and measurement-suitability gates are distinct; success prediction remains a proxy |
| 9 | PASS | Unchanged B3.1 calibration/qualification and localized_relative scope; wider-view generalization not established |
| 10 | PASS | L2 no-viable outcomes and 30 actual rejected-view diagnostic scans |
| 11 | PASS | Declared static geometry/no-go constraints |
| 12 | PASS | Recorded feasibility decisions |
| 13 | PASS | Explicit view/time/travel costs |
| 14 | PASS | Comparable P0/P1/P2/P3 |
| 15 | PASS | Coverage union and redundancy |
| 16 | PASS | Constrained multi-view recommendations |
| 17 | PASS | Persisted selection explanations |
| 18 | PASS | Explicit unsupported/no-viable outcomes |
| 19 | PASS | No physical mission authorization |
| 20 | PASS | Critical F1 advisories preserved |
| 21 | PASS | Actual closed-loop virtual inspection |
| 22 | PASS | Original imperfect Phase 2 measurements |
| 23 | PASS | Unchanged Phase 3/3.1 processing |
| 24 | PASS | Original F1 processing |
| 25 | PASS | Causal public-data replanning |
| 26 | PASS | PostgreSQL request/plan/review/result persistence |
| 27 | PASS | Authenticated backend API records |
| 28 | PASS | Actual 3D browser plan, frustum and result display |
| 29 | PASS | Predicted and qualified measured coverage have separate display conventions |
| 30 | PASS | Executed E5-A numerical/optimization checks |
| 31 | PARTIAL | E5-B executed all 2,160 comparisons; S01/S06/S07/S15 scenario fidelity is limited as documented |
| 32 | PASS | Identical primary inputs, candidates and budgets verified |
| 33 | PASS | Disjoint development and held-out seeds; no post-test weight tuning |
| 34 | PARTIAL | Coverage/detection/resource metrics reported; actual flight time, full-run terminal CPU accounting and full acquisition ablations remain unavailable |
| 35 | PASS | Ten actual numerical/geometric/browser figures |
| 36 | PASS | Import isolation and post-seal truth evaluation |
| 37 | PASS | Tested short planning load retained 30/30 current critical observations; full E4 remains open |
| 38 | PASS | P5-01 through P5-04 remain OPEN |
| 39 | PASS | 307 pytest tests, typing/lint/format, frontend build/tests and live integration |
| 40 | PASS | Reproducible validation report with explicit qualifications |
