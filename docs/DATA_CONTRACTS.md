# Data contracts

All persisted contracts carry schema_version 1.0.0. IDs are stable nonempty alphanumeric identifiers with `.`, `_`, `:`, `-` separators. Unknown fields are rejected. Breaking field/unit/semantic changes require a new schema version and explicit migration; regenerate schemas and run all consumers' tests. Optional additive fields still require consumer coordination because v1 rejects unknown fields.

| Contract | Responsibility |
|---|---|
| Asset | Hierarchy, geometry artifact, frame and parent/world pose, material, sensor associations, operating/baseline versions, regions, criticality |
| PlantState | Timestamped mode, normalized load, pressure Pa, process/ambient temperature degC and asset variables |
| SensorObservation | Scalar or vector measurement, compatible unit, uncertainty, quality, timestamps, sequence, provenance/location references |
| InspectionCapture | Mission, observed assets/regions, modality, artifact, sensor pose, calibration, coverage and quality |
| GeometricDetection | Baseline/current capture, region, displacement m, uncertainty m, algorithm/version, processing artifacts, optional justified confidence |
| EvidenceRecord | Source, hypothesis, acquisition/processing times, quality/uncertainty, context and validity |
| ConditionAssessment | Severity independent of confidence, evidence IDs, missing inputs, action/policy and review status |
| ScenarioDefinition | Reproducible controller configuration; includes private fault references, never sent to analytics |
| FaultInjection | Restricted category, interval, region, severity parameters and true process/geometric changes |
| DatasetProvenance | Dataset source, license/source URI, hybrid lineage, transformations, artifacts |
| ExperimentDefinition | E1–E4 inputs, outputs, planned metrics and pending baseline |
| ExperimentRun | Run/scenario/dataset IDs, seed, software/configuration versions, Git commit, timestamps, artifact/evaluation/test references |
| Artifact | Stable artifact ID, URI, media type and optional SHA256 |

Schemas are generated from Pydantic into schemas/*.schema.json; FaultInjection is exported under schemas/restricted. Exporting the schema does not expose instantiated private labels. Large point clouds and images remain external artifacts. URI references are metadata; Phase 0 does not dereference or verify their existence.

Asset types are open identifiers; initial conventions are boiler_water_wall_panel, steam_drum, steam_pipeline, structural_support, valve, fixed_reference_structure. Extending types does not require changing validation. Plant modes are shutdown, startup, steady_operation, load_transition, abnormal_operation.

Coordinates are right-handed: X east/configured plant X, Y north/configured plant Y, Z up. Local synthetic origins are not georeferenced. Distance is metres; computational angles radians. Frame kind is world, asset_local, sensor_local or registered_world, qualified by a reference ID. Frame equality includes both fields. T_target_source multiplies homogeneous column vectors from source into target. Composition T_c_b.compose(T_b_a) yields T_c_a; inversion reverses frames. Rigid matrices must be finite 4×4, bottom row [0,0,0,1], orthonormal with determinant +1 (absolute tolerance 1e-8). Asset poses map their frame to parent or world; capture poses map sensor-local to the capture frame.

Interface temperature is degC, pressure Pa, vibration RMS m/s2, normalized load dimensionless `1`; vector extension currently uses metres. Numeric values must be finite, uncertainty nonnegative, temperatures at least -273.15, pressure/vibration nonnegative and load in [0,1]. These are representation/physical constraints, not boiler safety thresholds. Additional vector types require explicit versioned unit semantics. Per-axis covariance is pending; scalar uncertainty has no implied confidence level.

UTC ISO-8601 timestamps must include Z or +00:00; naive and nonzero-offset inputs are rejected. acquired_at is measurement time, received_at is platform arrival, processed_at is optional completion time. Ordering requires acquired <= received <= processed when present. This assumes the configured clock domain; uncertain clocks are flagged rather than silently corrected. Simulation timestamps derive from start, step and time_step_s independently of wall-clock execution. Freshness uses acquisition age, not arrival. Per-observation delivery flags represent late, missing, duplicate and out-of-order delivery; detection/deduplication and temporal fusion are pending. Missing measurements can be represented by EvidenceRecord validity=missing without inventing a numeric sample.

Severity green/amber/red/unknown is separate from confidence supported/limited/insufficient/unknown. Unknown carries no healthy implication. Evidence validity is valid/stale/invalid/missing/inconclusive. Numeric detection confidence requires a confidence method reference; that reference alone does not establish calibration.

Public real-world manifests require license/source URI. Hybrid manifests require both real_source_ids and synthetic_transformations. Pending example manifests are templates and confer no external-data validation. Real and simulated records use identical public models and provenance references; analytics has no label/source-specific algorithm in Phase 0.


## Phase 1 compatible extensions (package 0.2.0)

Public observation shapes and units are unchanged. The schema_version remains 1.0.0: additions are optional fields or widened management-status enums, with coordinated schema regeneration and package upgrade. Old payloads load in the new package; old strict binaries may reject payloads using new fields/status values. Upgrade consumers before producing these additions. No claim of forward compatibility with frozen Phase 0 validators is made.

SensorConfiguration adds optional modality, coordinate_frame, pose, acquisition_parameters, calibration_reference, noise_model_reference and measurement_configuration. A supplied pose must map that sensor's local frame to its associated asset or a world frame. FaultInjection adds explicit spatial/evolution/persistence parameters; see FAULT_INJECTION.md. ExperimentDefinition implementation maturity now allows not_implemented/in_progress/implemented/validated. ExperimentRun carries an independent optional maturity field and run_outcome pending/passed/failed/error, while preserving its original evaluation_status. E1–E4 configurations remain not_implemented.

PlantConfig and SimulationManifest are simulator/controller configuration schemas; GroundTruthSnapshot is exported under schemas/restricted. Read views and snapshot dataclasses are deliberately excluded from analytics serialization. NPZ fields and mesh files hold physical state, not noisy observations. Hash-verified replay references are relative to the run root. Baseline GLB uses node transforms, while exported PLY/current GLB vertices are already world coordinates; do not transform them twice.


## Phase 2 extensions (package 0.3.0)

Existing schema_version 1.0.0 payloads remain readable. Optional additions require coordinated upgrade of strict consumers before producing new fields; frozen older validators may reject them. SensorObservation adds optional measurement_source (process/surface/phenomenological/operating_state), configuration_version and source_type. InspectionCapture adds optional artifact_coordinate_frame, configuration_version, source_type, numeric acquisition_parameters and reported per-axis translation/rotation standard deviations. Its existing coordinate_frame remains the target of sensor_pose; the new artifact frame identifies sensor-local payload coordinates. This avoids silently changing the old transformation convention. Reserved simulator/reference keys are rejected inside quality/acquisition metadata.

ObservationManifest extends management metadata using existing DatasetProvenance and Artifact contracts. It lists only public observation files and checksum references. AcquisitionConfig is a privileged controller schema, not an observation format. Public LiDAR NPZ keys are points_m and valid_returns; public thermal NPZ keys are temperature_c and valid_mask. NaN is used only for invalid thermal pixels with a false mask. PLY stores measured sensor-local points; the reported pose is needed for a world derivative. Camera fx/fy/cx/cy metadata uses +X-forward/+Y-left/+Z-up rays, with pixel right/down corresponding to -Y/-Z. No source triangle or exact asset label is attached to measured points.

IoT retransmissions intentionally reuse observation_id, acquisition timestamp and sequence number; received_at and delivery_status distinguish duplicates. Delivery flags describe transport, not evidence freshness/severity. JSONL is canonical; CSV is a companion. Public loaders reject private/traversal/symlink paths and unsupported array keys. Independent public datasets retain required licenses/source URIs and must be normalized into these same contracts. E1–E4 maturity remains not_implemented; sensor verification reports do not implement those future experiments.
