# Virtual sensing interfaces

Phase 2 (package 0.3.0) acquires measurements from the common Phase 1 physical world. It does not perform registration, anomaly classification, condition assessment or evidence fusion. Flat sensing modules correspond to config, noise, raycast, lidar, thermal, iot, acquisition, export, products and visualize; evaluation/sensing.py is a separate privileged verification tool.

`LidarSensor.capture` and `ThermalSensor.capture` accept a timestamped PhysicalReadView, event/provenance IDs, independent measurement/pose RNGs and an optional acquisition pose. They return CaptureProduct with a public InspectionCapture, allowlisted measured arrays, and a separate private diagnostic dictionary. `IoTSensor.capture` uses the physical reader at its actual jittered sample time and returns public SensorObservation records plus separate scalar references. generate_iot supplies batch scheduling; acquire orchestrates both forms. The optional read_process_at fast port returns actual process variables without constructing meshes; read_at remains the sufficient fallback. No hidden expected operating variables enter public records. Imaging poses may be world-relative or asset-parent-relative; the privileged read port supplies the current asset transform and the sensor resolves T_world_asset.compose(T_asset_sensor) before acquisition. Public records still expose only the reported world pose.

Open3D 0.19.0 CPU RaycastingScene is the primary first-visible-surface backend. The initially attempted cancellation did not prevent installation; import and CPU operation succeeded. An independently tested explicit numpy_bvh alternative uses double-sided triangle intersections and nearest-positive-hit selection. There is no implicit fallback to vertex sampling. The API image remains lightweight and does not install the optional Open3D stack.

Both imaging sensors use a right-handed local frame: +X optical/scan forward, +Y left, +Z up. T_world_sensor maps local column vectors to plant world. Camera columns run right (-Y) and rows down (-Z), unlike the conventional OpenCV +Z-forward camera frame. Measured LiDAR points are stored sensor-local. InspectionCapture.coordinate_frame is the target of the reported pose; artifact_coordinate_frame explicitly declares the payload frame. A world derivative must use sensor_pose (reported), never the hidden true pose. Camera arrays use pixel row/column coordinates with fx/fy/cx/cy in acquisition_parameters.

Configuration files configs/sensing/L0.yaml, L1.yaml, moderate.yaml and L2.yaml contain numeric noise, pose, range and delivery assumptions. They are simulator/controller configuration, not analytics inputs. L0 is ideal verification; L1 nominal; moderate is an intermediate L1 variant; L2 degraded. These are uncalibrated synthetic settings, not certified instruments. Nine IoT channels cover temperature, pressure, load and phenomenological RMS vibration; VL-01 and REF-01 have no direct IoT instruments. S0–S5 v3 enable all installed channels; older scenario payloads still validate and enable only their listed sensors. The controller now respects sensor_config_ids.

SHA256-derived streams use the master seed, logical scenario namespace, sensor ID, event ID and purpose. The logical run identity is the scenario/configuration acquisition, not the output directory or wall clock. Different event/sensor order leaves data unchanged. Per-modality streams separate pose and measurement draws. Dataset IDs include configuration/seed fingerprints; public acquisition and observation IDs are scenario qualified. No process-randomized Python hash is used.

## CLI

Install the full validated Python 3.12 Linux environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
pip install -e '.[dev,viz,sensing]' --no-deps
# Or resolve compatible versions: pip install -e '.[dev,viz,sensing]'
twinguard sensing lidar --scenario scenarios/S2.yaml --time 60 --output-dir output/lidar
twinguard sensing thermal --scenario scenarios/S3.yaml --time 60 --output-dir output/thermal
twinguard sensing iot --scenario scenarios/S1.yaml --output-dir output/iot
twinguard sensing simulate --scenario scenarios/S2.yaml --output-dir output/S2-sensing
twinguard sensing validate --run-dir output/S2-sensing
twinguard sensing visualize --run-dir output/S2-sensing
python scripts/validate_phase2.py --output-dir datasets/synthetic/generated/new-sensing-validation
```

`--config configs/sensing/L2.yaml` selects another installation. All output directories must be empty/new. Failed validation exits nonzero. Single acquisitions support arbitrary valid plant times, including the scheduled historical S5 inspection. Actual acquisition time is simulated UTC; received_at adds modeled transport delay. No streaming broker or network service runs here.

## Output and isolation

manifest.json is an ObservationManifest with DatasetProvenance, acquisition namespace, seed, software/configuration versions, public record references and SHA256 artifacts. observations/lidar contains NPZ points/missing-return mask, PLY XYZ and InspectionCapture JSON. observations/thermal contains temperature/mask NPZ, numeric NPY, capture JSON and optional false-color PNG. observations/iot contains canonical JSONL and companion CSV in delivery order. observations/sensor_installation.json contains known fixed-channel configuration/location/source metadata, with no true camera poses or reference measurements. visualizations holds measured-output plots and a separately labeled simulator-context coverage figure.

Evaluator-only plant_truth.json retains exact fault/plant replay context separately. True poses, actual pose errors (derivable from the separate references), noiseless distances/temperatures, triangle/asset IDs and IoT references stay under evaluation_private (0700 directory, 0600 files). The underlying scene context is private. Public products never contain these arrays. Reports compare against those private references and are explicitly verification artifacts. They are not ordinary analytics inputs.

Phase 3 must use core.observations.load_public_observations and load_capture_arrays. The loader follows only manifest-declared observations/ references and checks checksums; it rejects traversal, absolute paths and symlinks into private storage. It never recursively scans evaluation_private or reports. NPZ keys are closed allowlists and pickle loading is disabled. Existing analytics_json still rejects physical views, private envelopes and truth records. The recursive import audit now excludes the whole privileged sensing package from analytics/fusion/inspection/API code; public ingestion helpers live in core.observations. This is architectural isolation, not an OS sandbox against malicious same-user Python reflection.

## Public dataset import

Normalize local public/physical datasets to the same contracts and an ObservationManifest, preserving license, source URI, units, UTC acquisition/receipt times and provenance. validate_import_manifest verifies the manifest/files; load_public_observations validates records; load_capture_arrays validates measurement arrays. LiDAR accepts primary NPZ points_m or a point-only PLY with the declared frame (mesh input is rejected). Thermal canonical input is NPZ temperature_c plus bool valid_mask; retain NPY/PNG only as documented sidecars, and supply camera intrinsics/extrinsics. Time series use public JSON/JSONL; map CSV units/IDs/timestamps into SensorObservation before import. Public real-world manifests require license and source URI; hybrid lineage is preserved by DatasetProvenance. No datasets were downloaded or synchronized across unrelated sources.
