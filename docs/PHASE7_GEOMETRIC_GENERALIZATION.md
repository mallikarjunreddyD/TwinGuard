# Phase 7 geometric generalization

Baseline `a283713ef6ecfb8b7f883b76701e39ec22e8e5ce`; candidate software 0.8.0 frozen at `edae1e5`. B3.1 remains the default. B3.2 (`v3.2-view-v1`) is a separate optional view-conditioned healthy calibration method. Both retain localized relative wall displacement scope, original sensor imperfections, registration algorithm and gates, minimum engineering effect, patch sample requirements and significant-region machinery. No global/support displacement capability is added.

## Executed root-cause diagnosis

The retrospective controller reacquired no historical data and verified the old E5 per-method seals before the restricted evaluator opened true poses. In 30 E5-S01 healthy seeds and 60 selected scans per method, P0/P2 had 11 positive scans/regions and median scan normal-transform p95 error 2.798 mm; P1 had one positive scan and 1.752 mm; P3 had two and 1.828 mm. Corresponding healthy absolute patch p95 medians were 3.235, 2.755 and 2.801 mm. All used the same `0.003` noise calibration group despite differing view geometry. These are subset scan-level results, not replacements for historical E5 aggregate metrics. The associations motivate view-conditioned calibration; they do not identify a unique cause.

A new matrix executed **216 actual scan pairs**: six viewpoints, six new seeds, healthy and 20 mm targets, L0/L1/L2. Predictions were sealed before alignment-only oracle diagnostics. Original registration validity and uncertainty gates remained in the oracle diagnostic.

| Fidelity / target | Pairs | Valid original registrations/results | Actual / alignment-oracle region count |
|---|---:|---:|---:|
| L0 healthy | 36 | 24 | 0 / 0 |
| L0 20 mm | 36 | 24 | 35 / 30 |
| L1 healthy | 36 | 29 | 0 / 2 |
| L1 20 mm | 36 | 26 | 29 / 30 |
| L2 healthy | 36 | 0 | 0 / 0 |
| L2 20 mm | 36 | 0 | 0 / 0 |

Region counts include raw reported regions; they must not be read as qualified recall. The fresh matrix did **not** reproduce the historical healthy false positives across all views. Exact alignment did not uniformly improve output. Registration error, local sampling/common overlap, incidence and normals, patch margins, calibration-group mismatch and clustering remain interacting explanations. Finite samples and different view distributions limit causal attribution.

## Independent healthy calibration

The new campaign generated **600 actual healthy scan pairs**, 20 declared view domains × 15 fit + 15 independent screen seeds. Fit seeds 14000–14014 and screen seeds 14100–14114 are disjoint from development 13500–13505 and final 15000–15029. Requested baseline/current pose jitter is distinct from original reported-pose error. Invalid registration results are excluded from fitting; exclusion counts remain in the evidence.

Only **12/20 domains** have sufficient usable fit/screen support and nonempty empirical threshold maps. Eight remain explicitly unsupported. One supported planned domain needs an empirical multiplier about **20.09**, versus the original minimum 1.5, and another about 3.70. A large healthy envelope reduces sensitivity; it is not proof of geometric precision. A minimum of ten independent screen maxima gives weak tail resolution and no distribution-free 95% generalization guarantee.

The public applicability check binds sensor sampling/noise signature, reported baseline/current poses and frames, target asset and independent sample support. Translation/angle envelopes (0.15 m / 0.08 rad) are declared engineering domains, not learned probabilities. The actual capture is independently checked after acquisition. No truth pose or hidden footprint is used. Missing support produces **inconclusive**, not healthy. New model: `configs/validation/view_calibration.json`; original B3.1 calibration remains unchanged.

## Development tradeoff (not final validation)

On 180 fresh development pairs with realistic requested-pose variation and 0/10/20/30/50 mm targets:

| Method | Healthy positive scans | Localized faults / all fault scans | Qualified fault scans | Inconclusive / all scans | Applicable scans |
|---|---:|---:|---:|---:|---:|
| B3.1 | 2 / 36 | 121 / 144 | 124 | 26 / 180 | Original noise-domain rule |
| B3.2 | 1 / 36 | 47 / 144 | 48 | 120 / 180 | 60 / 180 |

This is **not an established overall improvement**. B3.2 abstains much more and loses substantial unconditional detection. Qualified-only results condition on different selected subsets and cannot establish superiority. No candidate tuning is allowed from final heldout outcomes without a new freeze and untouched partition.

## Evidence and reproduction

- Retrospective results: `experiments/outputs/phase7-V1-E5-diagnosis`; tracked `docs/phase7/V1_E5_diagnostics.json`.
- Matrix: `experiments/outputs/phase7-V1-view-matrix`; run `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/phase7_view_matrix.py --help` for explicit output controls.
- Calibration: `experiments/outputs/phase7-V1-view-calibration`; tracked `docs/phase7/V1_calibration_summary.json` and installed separate model.
- Development: `experiments/outputs/phase7-V2-development-detectors`.
- Freeze: `docs/phase7/CANDIDATE_FREEZE.json`, source commit `edae1e5`.
- Final untouched detector campaign: `experiments/outputs/phase7-V3-heldout-detectors`. Its results will be reported only with its completed journal and seed-cluster uncertainty.

All measurements above are synthetic software evidence. No surveyed instrument accuracy or relevant-environment validation is claimed.
