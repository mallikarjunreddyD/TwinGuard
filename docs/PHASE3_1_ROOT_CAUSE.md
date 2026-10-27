# Phase 3.1 root-cause diagnosis — frozen before production changes

The unchanged Phase 3 E1 rerun at source commit 775fc11 reproduces all B1/B2/B3 headline metrics exactly. It contains 154 scan pairs; B3 recall is 0/30 at 10 mm, 0/30 at 20 mm, 11/33 at 30 mm and 20/30 at 50 mm, region precision 0.800, healthy FPR 0/30, inconclusive fraction 35.065%, mean transform translation error 28.917 mm. Baseline source/configuration, all manifest hashes, sensing presets, thresholds, failures and runtime are preserved in phase3_1/baseline_v1.json with a SHA256 sidecar and full baseline_results.json. Initial regression: 160 tests passed.

Diagnostic seeds 1100–1103 are disjoint from development 2100–2109, healthy calibration 2200–2229 and held-out 4100–4129. These ranges and coverage categories were saved before changes. No held-out observations have been evaluated at this checkpoint. The seven sensing conditions each use four seeds and five amplitudes: 140 actual first-hit scan pairs. D1 compares actual alignment against true-pose alignment; oracle runs retain the same original uncertainty penalty and explicitly override the registration gate solely to isolate alignment. Raw traces also override the gate for unqualified estimates; these are not production positives. Every original E1 case has a separate trace. No sensor/plant implementation or original detector was altered.

## D1/D2: actual versus oracle and sensing isolation

Errors below compare normal-projected patch estimates against the analytical compact field at patch centers, not physical metrology or full-vector accuracy. Changing a patch changes its target support; pointwise truth and patch-averaged quantities are distinct. Missing raw estimates remain in the usable-trial counts.

| Condition | Actual raw MAE mm | Oracle raw MAE mm | Actual usable /20 | Oracle usable /20 | Actual normal error p95 mm | Actual / oracle localized candidates (16 positives) |
|---|---:|---:|---:|---:|---:|---|
| degraded | None | None | 0 | 0 | 45.333 | 0 / 0 |
| dropout-only | 1.589726393823053 | 1.5940526894254878 | 20 | 20 | 0.054 | 8 / 8 |
| ideal-changed | 3.5504213954547383 | 1.742055954511862 | 20 | 20 | 6.465 | 4 / 4 |
| ideal-same | 1.5805333326600413 | 1.5805333326600413 | 20 | 20 | 0.000 | 8 / 8 |
| nominal | 5.790604292019777 | 1.6604577958652107 | 19 | 20 | 33.072 | 5 / 7 |
| pose-only | 1.7554498076057001 | 1.5805333326600413 | 20 | 20 | 0.001 | 8 / 8 |
| range-only | 1.7485989315452728 | 1.7272430315717275 | 20 | 20 | 0.637 | 8 / 8 |

Range-only, pose-only and dropout-only use L0 geometry/acquisition with exactly the corresponding nominal L1 parameter group copied; the combined nominal and L2 conditions retain their original full presets. Same-seed acquisition IDs and ordering are fixed within each contrast. D2 ideal-same actual and oracle are separate alignments of the same actual rays, not mesh correspondences. Aggregate normal error is evaluated by applying estimated and true relative transforms to measured current points in the same reported-baseline frame. It is not equated to the norm of translation error. Reported-pose error can be recovered from the stored reported and private true matrices; per-case traces retain estimated transforms and all gate reasons.

## D3: measurement versus decision

The exact original rule is abs(d) - 1.5*max(surface spread, healthy floor, registration score) - 5 mm > 0. The pooled healthy floor is 9.325 mm, so even before extra penalties the effective threshold is about 19 mm. Surface spread includes deterministic tube curvature and changed sampling; it is not solely estimator noise. A single floor therefore suppresses measurable localized signals. The maximum operation avoids variance summation, but does not establish that this spread is the uncertainty of the median difference.

T0 stores raw error, T1 applies the 5 mm absolute screen, T2 applies the complete original rule, and diagnostic T3 uses the 95th percentile of scan-wise maximum absolute raw healthy residual from the five original independent healthy calibration pairs. This T3 threshold is 13.683930465933052 mm; it is a diagnostic empirical screen, not a nominal 95% confidence interval. T3 is not selected on test faults, and merely replacing the old floor with a scalar does not solve spatial/sampling bias. Patch flags and region clustering remain distinct from significance.

| Peak mm | Missed trials | Supported contributors (can overlap) | Earliest limiting stage counts |
|---|---:|---|---|
| 10 | 30 | {'uncertainty_penalty': 15, 'raw_below_absolute_threshold': 7, 'neighborhood_qualification': 7, 'localization_or_global_quality': 2, 'registration_quality_gate': 2} | {'uncertainty_penalty': 13, 'raw_below_absolute_threshold': 7, 'neighborhood_qualification': 7, 'localization_or_global_quality': 1, 'registration_quality_gate': 2} |
| 20 | 30 | {'uncertainty_penalty': 19, 'neighborhood_qualification': 10, 'registration_quality_gate': 2, 'localization_or_global_quality': 1} | {'uncertainty_penalty': 19, 'neighborhood_qualification': 9, 'registration_quality_gate': 2} |
| 30 | 22 | {'uncertainty_penalty': 11, 'neighborhood_qualification': 9, 'localization_or_global_quality': 2, 'registration_quality_gate': 4, 'coverage': 2} | {'uncertainty_penalty': 10, 'neighborhood_qualification': 6, 'localization_or_global_quality': 2, 'registration_quality_gate': 2, 'coverage': 2} |
| 50 | 10 | {'neighborhood_qualification': 10, 'registration_quality_gate': 1, 'localization_or_global_quality': 1} | {'neighborhood_qualification': 9, 'registration_quality_gate': 1} |

Attributions are supported by actual intermediate gates, counts and margins, not inferred from a miss alone. Raw-below-threshold is a measurement/decision boundary observation, not proof that the physical displacement was absent. Multiple contributions are retained. A registration residual can suppress patches without triggering the registration-quality gate. No arbitrary causal percentage decomposition is claimed.

## D4: scale and support

The physical field is compact (1-r²)^3 on an ellipse with X/Z radii 0.4/0.5 m. Its half-height core radii are about 0.182/0.227 m. Baseline patch radius is 0.18 m, normal radius 0.26 m and voxel size 0.01 m. D4 spans 0.08/0.12/0.18/0.28 m relative to this core and the 16-channel sampling. It retains actual raycast observations and the same eight-point/common-cell gates. The smaller radius is not automatically adequate where vertical beam spacing leaves few cells.

| Radius m | 10 mm mean peak estimate mm | 20 mm mean peak estimate mm | Healthy region trials /8 | 10 mm usable trials /8 |
|---|---:|---:|---:|---:|
| 0.08 | 9.670036177333351 | 19.169309248419705 | 0 | 8 |
| 0.12 | 9.387987621935327 | 18.82882954859483 | 3 | 8 |
| 0.18 | 7.1668722723587885 | 13.460079603850163 | 0 | 8 |
| 0.28 | 5.5477966942735755 | 11.087260322555661 | 0 | 8 |

These are oracle-aligned scale isolations across ideal-same and nominal changed-view acquisitions. The full JSON retains MAE, usability and region outcomes at every amplitude. Patch traces retain normals, point counts, spread-dominated score, direction, coverage and flags. Existing opposite-layer and controlled displacement tests plus the new Phase 3.1 numerical tests guard crossing/back-surface failures. Full tube-curvature transfer cannot be inferred from a plane test alone.

## D5/D6: coverage and registration geometry

Baseline coverage categories: {'adequate': 152, 'insufficient': 1, 'fully_occluded': 1}. Categories were fixed before held-out detection: zero returns fully occluded; <12 returns or <0.1 common-cell fraction insufficient; <0.25 common-cell fraction marginal; otherwise adequate. These grid-based sampling categories do not prove peak visibility. Restricted traces additionally retain peak-core returns, tangent point spacing and a wall-prior incidence proxy; actual per-triangle incidence was not retained by the sensor and is explicitly unavailable. None of these private labels enter production.

- point_to_point-all: 0/40 registration failures, median conditioning 0.00649047, translation mean mm 2.9633886768219746.
- robust_point_to_plane-all: 1/40 registration failures, median conditioning 0.00649047, translation mean mm 17.835792141206365.
- strict-stable-only: 40/40 registration failures, median conditioning 1.15104e-06, translation mean mm None.

REF-01 may have hundreds of observed returns yet its narrow planar geometry does not constrain all rigid degrees of freedom. The strict stable-only test never forces success. All-surface ICP comparisons and the original two-start robust fit are selected only by public fit/RMSE; private errors are used solely to evaluate them. Repetitive geometry and changed visibility remain plausible local-minimum mechanisms, not a proven unique explanation for every transform error.

## Evidence-supported ranking and corrective action

1. **Decision uncertainty and surface-dependent sampling variability:** dominant directly observed suppression at 10/20 mm. Separate geometric spread from measured healthy residual variability; calibrate the actual estimator on independent healthy scans, with a family-wise/cluster-aware screen rather than dividing by sqrt(N).
2. **Registration-induced normal bias under changed views:** oracle lowers nominal raw errors substantially. Investigate public robust common-mode/tilt residual removal for localized wall changes, explicitly qualifying the resulting relative measurement and its inability to establish uniform wall displacement. Preserve conventional/original outputs; do not claim a globally accurate rigid transform merely from a planar correction.
3. **Patch attenuation:** ideal 10 mm signals are attenuated even with correct alignment. Use smaller supported neighborhoods with multiple scales; retain sparse/rough/cross-surface qualification. Choose settings on development only.
4. **Local neighborhood qualification under L2:** region-level observability does not guarantee normals, correspondence and common-cell quality. Preserve abstention and report achieved coverage. Lowering thresholds cannot recover absent/unqualified measurements.
5. **Clustering/localization:** explicitly counted where thresholded candidates fail the minimum region size or localization. Some cases remain ambiguous between residual geometry and association; no unjustified causal fractions are assigned.

The 10/20 mm failure is a combination, with decision suppression directly demonstrated in measurable cases and measurement/registration/quality failures in others. Future physical sensor calibration and independent surveyed geometry remain required. B3.1 implementation must follow this checkpoint and preserve B3 verbatim/selectable. No Phase 4 work is authorized by these findings.
