# Phase dependencies and acceptance gates

| Phase | Depends on | Work and acceptance gate |
|---|---|---|
| 0 foundation | None | Install package; contracts/schema export; S0–S5 validate; spatial/time/isolation tests; API/CLI; deployment configuration and documentation. Actual outcomes/limitations in VALIDATION.md |
| 1 plant | 0 | Versioned geometry and operating-state simulation; private controlled faults; deterministic replay and physical plausibility tests |
| 2 sensing | 1 | LiDAR/thermal/IoT adapters with uncertainty/calibration; identical synthetic/physical interfaces and no label leakage |
| 3 analytics | 2 | Registration, deformation and operating-state residuals; E1/E2 baselines and independent evaluation |
| 4 fusion | 3 | Validity-aware temporal/hazard policies; E3 stale/missing/critical-event tests and confidence calibration |
| 5 inspection | 4 | Risk prioritization and viewpoint/coverage planning; constrained planning and measurable coverage benefit |
| 6 integration | 2–5 | Storage/replay, edge dashboard, offline behavior and latency; E4 and resource-budget validation |
| 7 validation | 1–6 | Independent public, physical and industrial relevant-environment trials; defensible evidence register, documented failure modes |

Phase 1 inputs are the exported Asset, PlantState, ScenarioDefinition, FaultInjection, SensorObservation, InspectionCapture, DatasetProvenance and ExperimentRun schemas; configs/system.yaml, assets.yaml, sensors.yaml; S0–S5 and private fault fixtures. Implement producers behind the existing interfaces without changing public payloads. New physical parameters belong in versioned controller configuration, never analytics observations. Resolve decisions in ASSUMPTIONS_AND_LIMITATIONS before treating configuration values as physical engineering models. This delivery stops at Phase 0.
