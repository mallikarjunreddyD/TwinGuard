"""Public persisted contracts. No fault or ground-truth imports are permitted here."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .spatial import Frame, Transform
from .time import UTC

ID = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Number = Annotated[float, Field(allow_inf_nan=False, strict=True)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: Literal["1.0.0"] = "1.0.0"


class Artifact(Contract):
    artifact_id: ID
    uri: Annotated[str, Field(min_length=1)]
    media_type: str
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None


class Asset(Contract):
    asset_id: ID
    name: str
    asset_type: ID
    parent_asset_id: ID | None = None
    geometry: Artifact
    coordinate_frame: Frame
    pose: Transform
    material: dict[str, str] = Field(default_factory=dict)
    sensor_ids: list[ID] = Field(default_factory=list)
    operating_reference_id: ID
    baseline_geometry_version: ID
    inspection_region_ids: list[ID] = Field(default_factory=list)
    criticality: str | None = None

    @model_validator(mode="after")
    def pose_frame(self):
        if self.pose.source != self.coordinate_frame:
            raise ValueError("Asset pose source must match coordinate_frame")
        if (
            self.coordinate_frame.kind == "asset_local"
            and self.coordinate_frame.reference_id != self.asset_id
        ):
            raise ValueError("Asset frame must reference this asset")
        expected = (
            Frame(kind="asset_local", reference_id=self.parent_asset_id)
            if self.parent_asset_id
            else Frame(kind="world", reference_id=self.pose.target.reference_id)
        )
        if self.pose.target != expected:
            raise ValueError("Pose target must reference parent asset or world")
        return self


class OperatingVariable(Contract):
    value: Number
    unit: Annotated[str, Field(min_length=1)]
    uncertainty: Nonnegative | None = None


class PlantState(Contract):
    state_id: ID
    timestamp: UTC
    plant_id: ID
    operating_mode: Literal[
        "shutdown", "startup", "steady_operation", "load_transition", "abnormal_operation"
    ]
    normalized_load: Probability
    process_pressure_pa: Nonnegative
    process_temperature_c: Annotated[float, Field(ge=-273.15, allow_inf_nan=False)]
    ambient_temperature_c: Annotated[float, Field(ge=-273.15, allow_inf_nan=False)]
    asset_variables: dict[ID, dict[str, OperatingVariable]] = Field(default_factory=dict)


class Timing(Contract):
    acquired_at: UTC
    received_at: UTC
    processed_at: UTC | None = None
    sequence_number: Annotated[int, Field(ge=0)] | None = None
    clock_quality: Literal["synchronized", "uncertain", "unknown"] = "unknown"
    delivery_status: Literal["normal", "late", "missing", "duplicate", "out_of_order"] = "normal"

    @model_validator(mode="after")
    def ordering(self):
        if self.received_at < self.acquired_at:
            raise ValueError("received_at precedes acquired_at")
        if self.processed_at is not None and self.processed_at < self.received_at:
            raise ValueError("processed_at precedes received_at")
        return self


class SensorObservation(Timing):
    observation_id: ID
    sensor_id: ID
    asset_id: ID
    measurement_type: Literal[
        "temperature", "pressure", "vibration_rms", "operating_load", "vector"
    ]
    value: Number | list[Number]
    unit: Literal["degC", "Pa", "m/s2", "1", "m"]
    uncertainty: Nonnegative | None = None
    quality: Literal["good", "degraded", "invalid", "unknown"]
    provenance_id: ID
    location_reference: ID

    measurement_source: (
        Literal["process", "surface", "phenomenological", "operating_state"] | None
    ) = None
    configuration_version: ID | None = None
    source_type: (
        Literal["synthetic", "public_real_world", "hybrid", "physical_experimental"] | None
    ) = None

    @model_validator(mode="after")
    def units(self):
        units = {
            "temperature": "degC",
            "pressure": "Pa",
            "vibration_rms": "m/s2",
            "operating_load": "1",
            "vector": "m",
        }
        if self.unit != units[self.measurement_type]:
            raise ValueError("Unit incompatible with measurement type")
        if self.measurement_type == "vector":
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("Vector measurements require nonempty numeric list")
        elif isinstance(self.value, list):
            raise ValueError("Scalar measurement required")
        elif self.measurement_type == "temperature" and self.value < -273.15:
            raise ValueError("Temperature below absolute zero")
        elif self.measurement_type in ("pressure", "vibration_rms") and self.value < 0:
            raise ValueError("Measurement must be nonnegative")
        elif self.measurement_type == "operating_load" and not 0 <= self.value <= 1:
            raise ValueError("Load must be normalized")
        return self


class InspectionCapture(Timing):
    capture_id: ID
    mission_id: ID
    asset_ids: list[ID] = Field(min_length=1)
    region_ids: list[ID] = Field(default_factory=list)
    sensor_id: ID
    modality: Literal["lidar", "thermal", "rgb"]
    artifact: Artifact
    coordinate_frame: Frame
    sensor_pose: Transform
    calibration_id: ID
    coverage_fraction: Probability | None = None
    quality_indicators: dict[str, Number] = Field(default_factory=dict)
    provenance_id: ID

    artifact_coordinate_frame: Frame | None = None
    configuration_version: ID | None = None
    source_type: (
        Literal["synthetic", "public_real_world", "hybrid", "physical_experimental"] | None
    ) = None
    acquisition_parameters: dict[str, Number] = Field(default_factory=dict)
    reported_translation_std_m: Nonnegative | None = None
    reported_rotation_std_rad: Nonnegative | None = None

    @field_validator("acquisition_parameters", "quality_indicators")
    @classmethod
    def no_private_metadata(cls, values):
        reserved = {
            "triangle_ids",
            "triangle_id",
            "asset_labels",
            "correspondences",
            "surface_mesh",
            "diagnostic_flags",
            "reference_temperature_c",
            "reference_pressure_pa",
        }
        if any(
            key in reserved
            or key.startswith(("true_", "fault_", "ground_truth", "expected_", "noiseless_"))
            for key in values
        ):
            raise ValueError("Privileged simulator metadata cannot be observation metadata")
        return values

    @model_validator(mode="after")
    def pose_frame(self):
        if self.sensor_pose.target != self.coordinate_frame or self.sensor_pose.source != Frame(
            kind="sensor_local", reference_id=self.sensor_id
        ):
            raise ValueError("Sensor pose must map this sensor into capture coordinate frame")
        return self


class GeometricDetection(Contract):
    detection_id: ID
    asset_id: ID
    baseline_capture_id: ID
    current_capture_id: ID
    region_id: ID
    displacement_m: Number
    displacement_uncertainty_m: Nonnegative
    quality_status: Literal["good", "partial", "invalid", "unknown"]
    algorithm_id: ID
    algorithm_version: ID
    detected_at: UTC
    confidence: Probability | None = None
    confidence_method: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def supported_confidence(self):
        if self.confidence is not None and not self.confidence_method:
            raise ValueError("Confidence requires scientific method reference")
        return self


class EvidenceRecord(Contract):
    evidence_id: ID
    asset_id: ID
    source_id: ID
    modality: Literal["fixed_sensor", "geometric", "thermal", "rgb"]
    acquired_at: UTC
    processed_at: UTC
    hypothesis_id: ID
    quality: Literal["good", "degraded", "unknown", "invalid"]
    uncertainty: Nonnegative | None = None
    uncertainty_unit: str | None = None
    operating_context_id: ID
    validity: Literal["valid", "stale", "invalid", "missing", "inconclusive"]
    provenance_id: ID

    @model_validator(mode="after")
    def ordering(self):
        if self.processed_at < self.acquired_at:
            raise ValueError("Processing precedes acquisition")
        if self.uncertainty is not None and not self.uncertainty_unit:
            raise ValueError("Uncertainty requires units")
        return self


class ConditionAssessment(Contract):
    assessment_id: ID
    asset_id: ID
    assessed_at: UTC
    severity: Literal["green", "amber", "red", "unknown"]
    confidence_status: Literal["supported", "limited", "insufficient", "unknown"]
    supporting_evidence_ids: list[ID]
    missing_or_invalid_evidence_ids: list[ID]
    recommended_action: str
    policy_id: ID
    policy_version: ID
    human_review: Literal["pending", "reviewed", "not_required"]


class DatasetProvenance(Contract):
    dataset_id: ID
    source_type: Literal["synthetic", "public_real_world", "hybrid", "physical_experimental"]
    description: str
    license: str | None = None
    source_uri: str | None = None
    real_source_ids: list[ID] = Field(default_factory=list)
    synthetic_transformations: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def lineage(self):
        if self.source_type == "hybrid" and (
            not self.real_source_ids or not self.synthetic_transformations
        ):
            raise ValueError("Hybrid datasets require real sources and synthetic transformations")
        if self.source_type == "public_real_world" and (not self.license or not self.source_uri):
            raise ValueError("Public datasets require license and source URI")
        return self


class OperatingPoint(Contract):
    operating_mode: Literal[
        "shutdown", "startup", "steady_operation", "load_transition", "abnormal_operation"
    ] = "steady_operation"
    offset_s: Nonnegative
    normalized_load: Probability
    temperature_reference_delta_c: Number = 0
    displacement_reference_delta_m: Number = 0


class InspectionSchedule(Contract):
    sensor_id: ID
    offset_s: Number
    modality: Literal["lidar", "thermal", "rgb"]


class ScenarioDefinition(Contract):
    scenario_id: ID
    version: ID
    description: str
    plant_model_reference: ID
    asset_ids: list[ID] = Field(min_length=1)
    simulation_start: UTC
    duration_s: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    time_step_s: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    random_seed: Annotated[int, Field(ge=0)]
    operating_profile: list[OperatingPoint] = Field(min_length=1)
    sensor_config_ids: list[ID]
    inspections: list[InspectionSchedule]
    fault_config_references: list[ID]
    dataset: DatasetProvenance
    output_directory: str

    @model_validator(mode="after")
    def intervals(self):
        offsets = [p.offset_s for p in self.operating_profile]
        if (
            self.time_step_s > self.duration_s
            or offsets[0] != 0
            or offsets != sorted(set(offsets))
            or offsets[-1] > self.duration_s
        ):
            raise ValueError("Invalid time step or operating-profile offsets")
        if any(i.offset_s > self.duration_s for i in self.inspections):
            raise ValueError("Inspection exceeds duration")
        return self


class SensorConfiguration(Contract):
    sensor_id: ID
    asset_id: ID
    source_type: Literal["synthetic", "public_real_world", "hybrid", "physical_experimental"]
    configuration_version: ID
    description: str

    modality: Literal["lidar", "thermal", "rgb", "iot"] | None = None
    coordinate_frame: Frame | None = None
    pose: Transform | None = None
    acquisition_parameters: dict[str, Number | str | bool] = Field(default_factory=dict)
    calibration_reference: ID | None = None
    noise_model_reference: ID | None = None
    measurement_configuration: dict[str, Number | str | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sensor_pose(self):
        if self.pose is not None:
            if self.coordinate_frame is None or self.pose.source != self.coordinate_frame:
                raise ValueError("Sensor pose source must match sensor coordinate frame")
            if self.coordinate_frame != Frame(kind="sensor_local", reference_id=self.sensor_id):
                raise ValueError("Sensor frame must reference this sensor")
            if self.pose.target.kind not in ("world", "asset_local"):
                raise ValueError("Sensor pose target must be world or parent asset")
            if (
                self.pose.target.kind == "asset_local"
                and self.pose.target.reference_id != self.asset_id
            ):
                raise ValueError("Sensor pose must reference associated asset")
        return self
