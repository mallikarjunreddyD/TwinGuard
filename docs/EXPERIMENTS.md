# Experiments

E1–E4 are versioned ExperimentDefinition configurations in experiments/. Their implementation_status is not_implemented. ExperimentRun records status, software/configuration version, seed, provenance reference, start/end, outputs and metric/test artifact references. The evaluator Protocol defines a future interface but implements no calculations. No detection accuracy or latency values have been generated.

| Experiment | Inputs | Outputs | Planned baseline and evaluation |
|---|---|---|---|
| E1 geometric | Reference/current clouds, acquisition metadata, registration config | Registered cloud, change map, regions, displacement, registration quality, runtime | Rigid alignment + nearest-neighbor distances; displacement/localization error, precision, recall, false-positive rate, runtime |
| E2 operating state | Measurement history, load profile, reference model | Predictions, residuals, abnormal events | Fixed threshold vs operating-state residuals; false-positive rate, recall, residual error, load-transition behavior |
| E3 fusion | Fixed, geometric, thermal evidence, operating state, validity | Assessment, support, action, confidence | Latest-value vs temporal/hazard policy; critical detection, missed events, false escalation, stale/missing behavior, decision latency |
| E4 integration | Scenario, streams, inspection artifacts | Status, records, events, recommendations, logs | Recorded replay; ingestion correctness, latency, completeness, offline behavior, reproducibility |

Baselines are planned, not implemented. Future metric definitions must document denominators, matching tolerance, time windows, class imbalance, confidence intervals and operating regimes before execution. Keep train/calibration/test scenarios and independent datasets separate. Evaluate ablations for operating-state conditioning, uncertainty and temporal validity. Physical and synthetic results must never be pooled without explicit stratification.

Artifact names use experiments/outputs/{experiment_id}/{run_id}/{artifact_id}, with validated path-safe identifiers. Artifact metadata includes URI, media type and optional SHA256. Preserve input/configuration references and hashes alongside outputs; record environment requirements using scripts/lock-environment.sh. Volatile execution times are metadata, not deterministic signal outputs. Completed evaluations require an end time and metric artifact references. Pending/not_implemented runs must not invent successful measurements.

Restricted labels are read only by the simulation controller and evaluator, never included in observation serialization. Synthetic experiment results will test controlled assumptions; independent public datasets test transfer where applicable; physical experiments test sensing and installation; industrial relevant-environment tests are a separate future validation gate. No such experiments have yet been executed.


Phase 1 supplies physical-state fixtures and simulator verification, not E1–E4 implementations or detection metrics. Implementation maturity and individual run outcomes are separate fields. All four experiment configurations remain not_implemented. Edge integration belongs to Phase 5 and risk-adaptive planning to Phase 6 under the canonical roadmap. The numerical report in PHASE1_VALIDATION.md checks simulator arithmetic/geometry only.
