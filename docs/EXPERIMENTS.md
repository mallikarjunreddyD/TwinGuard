# Experiments

E1 and E2 are implemented in Phase 3; E3 fusion and E4 integration remain not_implemented. ExperimentDefinition points to typed benchmark configuration with disjoint calibration/evaluation seed sets. The driver generates imperfect measurements, freezes healthy calibration and configuration, saves/seals inference outputs, then invokes the restricted evaluator. Every method sees the same test observations. Defaults and split choices are fixed before test metrics; no held-out threshold optimization occurs.

E1 compares B1 reported poses + fixed NN, B2 conventional ICP + fixed NN and B3 robust ICP + patch uncertainty. Full matrix: 154 pairs across L0/L1/L2, same/changed views, 0/10/20/30/50 mm, five seeds and four stress/support cases. E2 compares static, conditioned and quality-aware operating references plus static/conditioned thermal models: 30 sequences, 150 thermal frames, six groups and five seeds. Full commands and actual values appear in PHASE3_VALIDATION.md; configs/experiments/*-smoke.yaml define the smaller smoke matrices.

Metric definitions: overall positive recall retains inconclusive/unobservable positives as misses; healthy FPR divides by all negative trials and therefore must be read alongside abstention and qualified-healthy denominators. An unflagged negative in a binary confusion table is not proof of health. E1 localized region precision counts unmatched/extraneous regions as false positives. Per-case sensor range error, transform error, qualified-patch displacement error and matched-region centroid error are distinct. Wilson intervals apply to trial proportions, not the patch engineering-score envelope. E2 FPR is a per-sequence mean over negative observations; temporal samples are correlated. Thermal summary separately reports inconclusive fraction, valid/saturated coverage, mask IoU and residual MAE. Units are never pooled for residual RMSE.

Calibration data, resolved algorithm settings, hashes, seeds, sensor presets and per-case private scenarios persist with generated runs. prediction_ready seals are verified before truth reads; tampered artifacts fail evaluation. Large datasets/predictions are ignored by Git, small measured reports/figures are retained under docs/. Same-identity filesystem access remains a deployment isolation limitation. No physical experiment, E3/E4 result or TRL certification is claimed.


## Phase 3.1 update

Phase 3.1 uses source baseline 775fc11 and predeclared disjoint seeds: diagnostic 1100–1103, development 2100–2109, healthy calibration 2200–2229, held-out 4100–4129. Healthy seeds split at 2215 into fit/screen groups. The held-out design has 900 principal pairs (30 independent seeds x three fidelities x five amplitudes x two paired views), plus 30 L2 stress pairs. Fault centers/extents vary according to the predeclared partition file. No production sensor/noise or deformation kernel is changed; all four methods see each identical public pair.

Reproduction on a fresh checkout with empty generated phase3_1 outputs:

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python scripts/phase31.py baseline
python scripts/phase31.py diagnose
python scripts/phase31.py development-data
python scripts/phase31.py calibrate
python scripts/phase31.py develop
# Verify candidate/source/calibration freeze; do not tune after held-out metrics.
python scripts/phase31.py heldout
python scripts/phase31.py figures
```

The held-out script refuses an existing output and verifies frozen source/model hashes before starting. The committed freeze describes this exact candidate; editing algorithms requires a new untouched partition. Scripts preserve original baseline reports rather than substituting held-out measurements. Git HEAD at execution and per-artifact hashes/provenance are recorded. Plotting source data and all eight figures live under docs/phase3_1 and docs/figures/phase3_1. Reports include overall and conditional recall, abstention, per-fidelity/amplitude counts, raw/qualified/unqualified error and missing-estimate counts. Paired bootstrap uncertainty resamples independent seeds, preserving within-seed/view dependence. It does not calibrate engineering uncertainty scores.


## Phase 4 update

E3 is implemented with separate E3-A controlled-semantic and E3-B actual-analytics tracks and a fixed F0 two-signal comparator versus F1. configs/experiments/E3.yaml declares fresh seeds, frozen models, cadence, availability assumptions and matching. Research metrics are post-seal and separate by track; no combined headline accuracy is justified. E4 remains unimplemented. See EXPERIMENT_E3.md and PHASE4_VALIDATION.md.
