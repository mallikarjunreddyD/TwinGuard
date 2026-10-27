# Phase 3.1 corrections and measurement semantics

The frozen root-cause report precedes these corrections; diagnostic Git checkpoint f03c186 preserves the baseline and D1–D6 evidence. Original geometry.py and registration.py remain byte-for-byte unchanged and B3 remains selectable. B1/B2/B3.1 are explicit method selections; no fault label selects a detector.

B3.1 reuses the measured conventional point-to-point ICP solution used by B2. D6 found lower transform error for this solution than the original robust fit on the tested diagnostic subset, while REF-01-only geometry was always weakly constrained. This is a scoped selection, not proof that point-to-point ICP is universally superior. Registration quality gates are retained and registered exports still describe that rigid solution. B3.1 does not silently claim that its later normal-direction correction improved all six rigid degrees of freedom.

The local estimator runs the original qualified normal-projected estimator at 80 and 120 mm radii, retaining original sample-count, roughness, normal, depth-layer and common-coverage checks. D4 related these scales to the compact deformation core and actual LiDAR sampling. Smaller scales recover localized peaks but can create isolated false candidates, so they require calibration and spatial support.

For each scale, valid oriented wall-patch estimates d are robustly fit to a broad residual plane b0+b1*x+b2*(z-1.5), using 12 IRLS iterations and a robust residual scale. At least 30 valid patches spanning 0.6 m in both tangent directions are required. The fitted component is removed before local screening. This removes broad pose/sampling residuals; it can also remove uniform or broad real wall motion. Therefore **all B3.1 values are localized wall-relative measurements**, explicitly tagged measurement_basis=localized_relative. B3 remains available for the original absolute comparison. A local negative is not evidence against global displacement. Support movement is not calibrated by this wall model and remains unavailable.

Calibration uses only measured healthy pairs from seeds 2200–2229 (three noise profiles and two viewpoints). Seeds 2200–2214 fit per-patch/per-scale bias and the 90th-percentile absolute residual envelope (minimum 0.5 mm); seeds 2215–2229 independently calibrate the complete scan-level spatial decision. Each spatial calibration cell requires ten healthy fits. Noise grouping uses only public range_sigma_m, not fidelity/fault labels or true poses. There is no point-count sqrt(N) reduction.

For each supported scale/location, corrected d = relative estimate - healthy bias. The normalized screen is (abs(d)-2 mm)/s, where s is the healthy residual envelope. Select the strongest supported scale at each center, then require at least two neighboring significant patches. The multiplier is max(1.5, empirical 95th percentile of the independent healthy scans' largest neighboring-pair minimum score). This calibrates the actual scale selection and correlated spatial rule rather than a hypothetical pointwise distribution. Finite-sample calibration is an engineering screen, not a calibrated 95% confidence interval or population false-alarm guarantee. The 2 mm engineering minimum was fixed before development scoring; it was not chosen on held-out outcomes.

L0 and L1 have adequate healthy calibration support; the existing L2 local estimator does not, so B3.1 abstains instead of lowering quality gates. No sensor, noise, pose-error distribution or physical deformation kernel is changed. Development comprises 300 independent acquired scan pairs (ten seeds, three profiles, five amplitudes, two views). The initial candidate detects 160/240 positives versus original B3's 60/240, with 0/60 versus 2/60 healthy alarms. B3.1 still abstains on all 100 L2 cases; these development metrics do not establish independent performance. No settings were retuned after this development comparison.

Contracts add optional patch raw_displacement_m, registration_component_m, scale_m and calibration_support fields. GeometryResult adds the multiscale_calibrated method, v3.1 algorithm version, measurement_basis, processing configuration hash, quality flags and reinspection_candidate. Existing fields/defaults remain loadable; schemas are regenerated. Capture/model/reference/registration links, oriented displacement, coverage, margin and quality remain available for future fusion. A no-change result means no significant localized change at the achieved sensitivity and coverage, never guaranteed equipment health. No hazard severity or Phase 4 fusion is implemented.

Example selection:

```bash
twinguard analytics geometry --baseline /path/to/public-baseline.npz \
  --current /path/to/public-current.npz --methods B1 B2 B3 B3.1 \
  --calibration experiments/outputs/phase3_1/baseline-reproduction/geometry_calibration.json \
  --improved-calibration experiments/outputs/phase3_1/b31_calibration_v1.json \
  --output-dir output/new-geometric-comparison
```

Use scripts/phase31_calibrate.py for the declared healthy calibration collection. Frozen calibration verifies the resolved AnalyticsConfig and accepted-reference hashes; mismatched configurations are rejected rather than silently reused. No oracle or evaluator imports enter production analytics.
