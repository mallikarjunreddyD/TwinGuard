# Phase 7 measurement-qualified planner

P0/P1/P2/P3 remain available. **P3v2** (`p3v2-view-v1`, software 0.8.0) is an explicit candidate, not the default and not an established research improvement. Its source and healthy model were frozen at `edae1e5` before final heldout trials.

P3v2 uses public, causally available baseline capture pose/configuration and measured associated surface cells. Candidate utility combines predicted common baseline overlap, sampling resolution/incidence, accepted-map normal conditioning, independent healthy calibration applicability/support and the empirical healthy decision envelope. The declared 10 mm inspection objective supplies a sensitivity proxy; no hidden test amplitude or footprint enters the score. Actual post-acquisition applicability and unchanged registration gates remain authoritative.

Weights are measurement area 0.40, deficiency 0.25, risk 0.20, cost 0.10 and redundancy 0.05. Positive terms are multiplied by the engineering measurement-quality proxy. These scores are **not calibrated detection probabilities** or physical safety probabilities. A high score cannot establish registration accuracy. The conditioning predictor uses nominal accepted-map normals; actual observed conditioning can differ.

The planner binds its policy hash to method version, configuration, healthy model hash, weights, objective and ablation. It preserves the source snapshot hash even in a history ablation. Backend queued requests freeze the healthy-model digest and refuse execution after model replacement. Baseline metadata is attached after a completed actual inspection; the API does not perform hidden private raycasting. Required-region cells must belong to their declared asset. Complete coverage of an explicitly scoped region can support continuing monitoring of that scope; other hazards remain unknown.

All existing route, access, standoff, calibration and resource constraints remain. Critical process findings remain independent of UAV inspection and require operator review. A reviewed recommendation permits simulation only. No flight/process command endpoint is added. Thermal observations are outside this geometric measurement model; equivalent calibration does not exist for every plant asset. Explicit rejection or manual/alternative inspection is preferable to an unsupported healthy conclusion.

## Development outcomes

Sixteen paired development cases (eight families, two seeds), each method evaluated under the same B3.1 or B3.2 detector, produced:

| Detector | Planner | Executed views | New localized cases | Healthy positive cases | Inconclusive acquisitions |
|---|---|---:|---:|---:|---:|
| B3.1 | P0 | 24 | 6 | 2 | 6 |
| B3.1 | P1 | 24 | 5 | 0 | 1 |
| B3.1 | P2 | 24 | 6 | 2 | 6 |
| B3.1 | P3 | 24 | 6 | 1 | 0 |
| B3.1 | P3v2 | 4 | 0 | 0 | 0 |
| B3.2 | P0 | 24 | 6 | 0 | 12 |
| B3.2 | P1 | 24 | 1 | 0 | 8 |
| B3.2 | P2 | 24 | 6 | 0 | 12 |
| B3.2 | P3 | 24 | 2 | 1 | 6 |
| B3.2 | P3v2 | 8 | 1 | 0 | 2 |

The conservative candidate selects very few views. Its smaller false-positive and inconclusive counts partly reflect fewer acquisitions. These development results do not establish superior yield or recall and do not justify promotion. Final seed-paired comparisons must include all initial/final outcomes, abstention, qualified area and view budgets.

## Evaluation boundaries

The new paired controller persists/seals plans before actual imperfect acquisitions, shares identical observations for identical requested views within a case, and runs unchanged F1. It compares all five planners under both common detectors to separate planner and detector effects. Adaptive methods replan only from public completed results within the original remaining budget. Ablation output roots acquire again, rather than rescoring the old result table.

The current eight-family campaign has healthy wide views, unconfirmed/partial initial evidence, stale evidence, L2, load transitions, competing metadata and critical access policy controls. **It does not yet implement an independent environmental occluder or verify a sufficient scoped-coverage control.** Competing assets retain explicit unequal calibration limits. Critical access here is declared policy metadata, not a measured pressure test; actual critical-pressure validation is performed separately in V4. These are incomplete validation requirements, not passed scenarios.

Reproduce with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/phase7_planner_study.py --output <new-output> --partition heldout --workers 2`. Add `--ablations` for six actual acquisition ablations on the same heldout seed range. Output directories must be new; `--resume` verifies journal configuration and checkpoint digests.
