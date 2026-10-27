# Canonical phases and gates

| Phase | Scope | Dependencies and acceptance gate |
|---|---|---|
| 0 | Architecture, data contracts, and development environment | Versioned contracts; spatial/time/isolation tests; API/CLI; reproducible setup. Historical evidence: VALIDATION.md |
| 1 | Industrial plant digital twin and fault simulation | Phase 0; executable seven-asset world, operating dynamics, physical faults, persistent state, isolated truth, export/replay and measured checks. Evidence: PHASE1_VALIDATION.md |
| 2 | Virtual LiDAR, thermal, and IoT sensing | Phase 1 physical read port; calibration, uncertainty, partial/noisy acquisition, identical synthetic/real observation interfaces and no label leakage |
| 3 | Registration, geometric change detection, and operating-state analytics | Phase 2; E1/E2 baselines and independent evaluation |
| 4 | Hazard-aware and temporally consistent evidence fusion | Phase 3; E3 stale/missing/critical-event tests and confidence calibration |
| 5 | Edge platform, industrial communication, and dashboard | Phases 2–4; storage/replay, MQTT/OPC UA where required, offline/resource/latency behavior and E4 integration |
| 6 | Risk-adaptive inspection and viewpoint planning | Phases 4–5; constrained prioritization and measurable coverage benefit |
| 7 | Experimental validation and TRL evidence package | Phases 1–6; independent public, physical and relevant-environment evidence; reproducible procedures and failure analysis |

This numbering supersedes the Phase 0 planning order that placed inspection at 5 and integration at 6. Historical validation records describe the implementation at their original date and are retained.

Phase 2 entry points are `PlantSimulator.sensing_reader().read_at(time_s)` and `PhysicalStateReader`. Read views expose world-space triangle surfaces, per-vertex temperatures and process variables without injection labels. SensorConfiguration supplies optional modality, frame, pose, acquisition, measurement, calibration and noise references. Mesh and state metadata carry world/model references. The sensor layer must implement calibration, ray intersections, thermal projection/interpolation, timing, uncertainty and noise. Those algorithms remain missing by design. It must emit existing public observations through analytics_json; truth geometry/state objects are never analytics inputs. No Phase 2 acquisition is implemented here.
