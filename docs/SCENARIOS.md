# Scenarios and replay

S0–S5 v2 are executable synthetic plant scenarios, not calibrated industrial limits. Each records ID/version, canonical seven-asset plant, UTC start, duration/step, seed, load profile, sensor configurations, inspection schedule, private injection references, provenance and output location. The deprecated wall-01 alias still validates historical fixtures; runtime resolves it to BW-01.

| Scenario | Implemented behavior |
|---|---|
| S0 | Steady load 0.5, process reference T/P, no fault |
| S1 | Load ramps 0.5→0.8 over 60 s; coupled lagged T/P; normal axial expansion; no fault |
| S2 | Baseline LiDAR event at 0 s; wall bulge begins 30 s, grows to 30 mm at 60 s; second LiDAR event at 60 s; structural change persists after end_at=90 s |
| S3 | Local +12 degC thermal residual, injection 30–90 s, ten-second recovery |
| S4 | Process pressure residual +200000 Pa, injection 30–90 s, ten-second recovery; no fabricated geometry/hotspot |
| S5 | LiDAR event at -3600 s; process disturbance starts +90 s and remains active through the run end at 120 s; no freshness decision |

These events schedule future sensor acquisition only; no scans, camera images or noisy measurements are produced. Negative inspection offsets reference an initial historical plant held at initial conditions before t=0. Defaults export 0, 60, run end and every scheduled inspection time, while the process trace follows the exact time grid including a final partial interval if necessary. Snapshot geometry is generated only at selected times.

`load_scenario` validates against configs/assets.yaml and sensors.yaml and checks private fault intervals/references. PlantConfig separately validates geometry dimensions and topology. Simulator construction resolves aliases and rejects physical faults on absent/inappropriate assets. `twinguard validate-config` preserves the Phase 0 metadata check; simulation also validates plant/fault feasibility.

Example independent profiles P0–P4 reside under configs/profiles; they are full valid scenario configurations. Run them with `twinguard plant simulate --scenario configs/profiles/P2.yaml --output-dir output/P2`. Operating profiles are linearly interpolated and first-order responses evaluated analytically; elapsed wall-clock time never controls simulation time.

Runs save a complete plant configuration, private scenario/fault copies, versions, Git commit/dirty flag, source-tree digest, seed, provenance, timestamps and SHA256 artifacts. `load_run` verifies artifact hashes before reconstructing the world independently of repository configuration files. Numerical repeatability is asserted within the pinned environment. Wall-clock timestamps/runtime and container build bytes are not claimed to be identical between runs. The source digest identifies dirty code; preserve or commit the matching source for long-term replay.

Artifact IDs derive from relative paths and remain stable as snapshots are added. Time tokens preserve full binary-float round-trip precision. Each snapshot export appends a matching restricted truth record before refreshing artifact checksums.


Phase 2 migration: S0–S5 are now v3 and enable the nine fixed channels plus LiDAR/thermal instruments in configs/sensors.yaml. Physical plant/fault behavior, seeds, intervals and S2/S5 inspection timings are unchanged. Older v2 scenarios still validate and the acquisition controller respects their smaller enabled lists. configs/sensing/* supply acquisition/noise parameters independently of plant physics. Run `twinguard sensing simulate --scenario scenarios/S2.yaml --output-dir output/new-S2-sensing`. Public observations and sensor-model private references occupy a separate sensing run rather than being mixed into the Phase 1 true-mesh dataset.
