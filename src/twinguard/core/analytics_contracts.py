"""Truth-free qualified analytics outputs; no final condition severity or fusion."""

from typing import Literal
from pydantic import Field
from .contracts import Contract, ID, Number, Nonnegative, Probability, GeometricDetection, Artifact
from .spatial import Transform, Frame
from .time import UTC

Status = Literal[
    "valid", "inconclusive", "invalid", "insufficient_coverage", "out_of_reference_range"
]
Vector = tuple[Number, Number, Number]


class RegistrationResult(Contract):
    registration_id: ID
    baseline_capture_id: ID
    current_capture_id: ID
    transform_convention: Literal["T_baseline_current"] = "T_baseline_current"
    transform: Transform
    method: Literal["pose_only", "point_to_point", "robust_point_to_plane"]
    algorithm_version: ID = "v1"
    status: Status
    converged: bool
    fitness: Probability
    inlier_rmse_m: Nonnegative | None
    correspondence_count: int = Field(ge=0)
    conditioning_ratio: Nonnegative
    uncertainty_score_m: Nonnegative
    repeatability_m: Nonnegative
    quality_flags: list[str]
    runtime_s: Nonnegative
    registered_artifact: Artifact | None = None
    registered_coordinate_frame: Frame | None = None


class PatchEstimate(Contract):
    patch_id: ID
    asset_id: ID | None
    center_world_m: Vector
    normal_world: Vector
    direction: Literal["oriented", "unsigned", "unreliable"]
    baseline_points: int
    current_points: int
    common_coverage: Probability
    displacement_m: Number | None
    uncertainty_score_m: Nonnegative | None
    engineering_margin_m: Number | None
    threshold_m: Nonnegative
    raw_displacement_m: Number | None = None
    registration_component_m: Number | None = None
    scale_m: Nonnegative | None = None
    calibration_support: int = Field(default=0, ge=0)
    significant: bool | None
    status: Status
    quality_flags: list[str]


class GeometryRegion(Contract):
    region_id: ID
    asset_id: ID | None
    association_status: Literal["associated", "ambiguous"]
    bounds_world_m: tuple[Vector, Vector]
    representative_displacement_m: Number
    uncertainty_score_m: Nonnegative
    patch_ids: list[ID]
    area_estimate_m2: Nonnegative
    legacy_detection: GeometricDetection | None = None


class GeometryResult(Contract):
    analysis_id: ID
    baseline_capture_id: ID
    current_capture_id: ID
    acquired_at: UTC
    method: Literal["nearest_neighbor", "patch_screening", "multiscale_calibrated"]
    algorithm_version: ID = "v1"
    registration_id: ID
    reference_id: ID
    calibration_id: ID
    status: Status
    asset_statuses: dict[ID, Status] = Field(default_factory=dict)
    patches: list[PatchEstimate]
    regions: list[GeometryRegion]
    significant: bool | None
    sensitivity_statement: str
    measurement_basis: Literal["absolute", "localized_relative"] = "absolute"
    reinspection_candidate: bool = False
    processing_configuration_sha256: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    runtime_s: Nonnegative


class OperatingPrediction(Contract):
    prediction_id: ID
    observation_id: ID
    sensor_id: ID
    asset_id: ID
    acquired_at: UTC
    available_at: UTC
    model_id: ID
    method: Literal["static", "conditioned", "conditioned_quality"]
    observed_value: Number
    estimated_reference: Number | None
    residual: Number | None
    uncertainty_score: Nonnegative | None
    threshold: Nonnegative | None
    unit: str
    significant: bool | None
    status: Status
    quality_flags: list[str]


class ThermalRegion(Contract):
    region_id: ID
    image_bounds: tuple[int, int, int, int]
    pixel_count: int
    asset_id: ID | None
    association_status: Literal["associated", "image_only", "ambiguous"]
    peak_residual_c: Number
    median_residual_c: Number
    uncertainty_score_c: Nonnegative


class ThermalResult(Contract):
    analysis_id: ID
    capture_id: ID
    acquired_at: UTC
    model_id: ID
    method: Literal["static", "conditioned"]
    status: Status
    valid_pixels: int
    saturated_pixels: int
    total_pixels: int
    saturation_known: bool
    regions: list[ThermalRegion]
    significant: bool | None
    quality_flags: list[str]
