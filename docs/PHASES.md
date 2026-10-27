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

Phase 2 entry points are `PlantSimulator.sensing_reader().read_at(time_s)` and `PhysicalStateReader`. Read views expose world-space triangle surfaces, per-vertex temperatures and process variables without injection labels. SensorConfiguration supplies optional modality, frame, pose, acquisition, measurement, calibration and noise references. Mesh and state metadata carry world/model references. Phase 2 now implements first-hit ray intersections, thermal interpolation/projection, assumed calibration/noise, timing and uncertainty controls. Physical calibration and hardware adapters remain pending. It must emit existing public observations through analytics_json; truth geometry/state objects are never analytics inputs. Phase 2 acquisition is implemented; no Phase 3 analytics is implemented.


Phase 2 evidence is recorded in PHASE2_VALIDATION.md. Phase 3 receives InspectionCapture/SensorObservation records through core.observations.load_public_observations and measured arrays through load_capture_arrays. Baseline/current scan IDs, reported poses/standard deviations, intrinsics, numeric thermal arrays/masks and UTC measured process streams are sufficient to start analytics without simulator access. Point matching, registration, operating-reference fitting, change detection and anomaly classification remain Phase 3 work. Only the separate evaluator may use evaluation_private references and exact fault records. No missing sensing contract requires Phase 3 to access true poses or hidden expected operating values.


## Phase 3 update

Phase 3 is now implemented and validated in PHASE3_VALIDATION.md; earlier statements above about pending analytics are historical handoff context. Public observations now support ICP, geometric regions and operating/thermal residuals without simulator truth. E1/E2 run; E3/E4 remain pending. Phase 4 must preserve missing/invalid/OOR qualifications and cannot equate no detection with healthy equipment.


## Phase 3.1 update

Phase 3.1 is a corrective research/validation increment within canonical Phase 3. It preserves original B3 and adds a calibrated wall-relative B3.1; it does not renumber phases or begin Phase 4. Fusion must distinguish relative localized measurements, original absolute comparisons and unavailable/insufficient evidence. See PHASE3_1_ROOT_CAUSE.md, PHASE3_1_IMPROVEMENTS.md and PHASE3_1_VALIDATION.md.
