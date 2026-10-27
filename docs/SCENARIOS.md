# Scenarios

S0–S5 are small synthetic test configurations, not simulation outputs or calibrated industrial limits. Each records version, plant/assets, UTC start, duration, step, seed, operating profile, sensor configuration IDs, inspection schedule, fault references, dataset provenance and output location.

| ID | Intended future behavior |
|---|---|
| S0 | Healthy steady operation, no faults |
| S1 | Load rises 0.5 to 0.8 at 60 s; expected temperature/displacement reference changes 8 degC/0.002 m |
| S2 | Localized wall deformation 0.030 m, restricted fault-S2 |
| S3 | Hotspot +12 degC relative to operating reference, restricted fault-S3 |
| S4 | Process pressure deviation +200000 Pa; label is a future critical-event test, not an engineered threshold |
| S5 | LiDAR inspection at -3600 s with a recent fixed-sensor context; process event at +90 s in fault-S5; complete temporal semantics pending Phase 4 |

Negative inspection offsets explicitly represent historical captures; operating profile offsets are ordered, unique, begin at zero and stay inside the simulation duration. Future streams must use simulated acquisition times while recording actual or replay reception time consistently. Fault intervals must lie within the scenario, and asset/sensor references must exist. `load_scenario` checks the repository catalog; standalone JSON Schema validation checks shape only and cannot resolve references.

Run `twinguard validate-config scenarios/S2.yaml`; `twinguard list-scenarios` validates and lists the collection. Controller configurations and faults must be given only to the simulator/evaluator. Future replay must record the scenario/configuration versions, input hashes, seed, package/environment lock and Git revision in ExperimentRun and retain artifact checksums. Pinning seeds alone does not promise identical outputs across library versions or hardware. Phase 0 round-trip tests establish configuration preservation only; simulator reproducibility is pending.
