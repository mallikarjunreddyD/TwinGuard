"""Public, finite planning records. Scores are engineering proxies, never failure probabilities."""

from twinguard.core.time import UTC
from typing import Annotated, Literal
from pydantic import Field, model_validator
from twinguard.core.contracts import Contract, ID, Probability, Nonnegative
from twinguard.core.spatial import Transform

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Vector = tuple[float, float, float]


class Box(Contract):
    lower: Vector
    upper: Vector

    @model_validator(mode="after")
    def ordered(self):
        import numpy as np

        if not np.isfinite([self.lower, self.upper]).all() or any(
            a >= b for a, b in zip(self.lower, self.upper)
        ):
            raise ValueError("Box requires ordered finite bounds")
        return self


class PlanningConfig(Contract):
    configuration_id: ID = "inspection-v1"
    reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_path: str = "configs/edge/plant.glb"
    sensor_path: str = "configs/sensing/L1.yaml"
    criticality: dict[str, Probability] = Field(default_factory=dict)
    allowed_volume: Box
    no_go: list[Box] = Field(default_factory=list)
    map_complete: bool = False
    minimum_standoff_m: Positive = 0.5
    maximum_range_m: Positive = 8
    safety_margin_m: Nonnegative = 0.2
    altitude_m: tuple[Nonnegative, Positive] = (0.5, 6)
    start_world_m: Vector = (0, 3.4, 1.65)
    speed_m_s: Positive = 0.5
    acquisition_s: Positive = 8
    return_to_start: bool = True
    cell_m: Positive = 0.08
    association_m: Positive = 0.06
    freshness_s: Positive = 3600
    stand_off_shells_m: list[Positive] = Field(default_factory=lambda: [2.5, 3.4])
    azimuths_rad: list[float] = Field(default_factory=lambda: [-0.35, 0, 0.35])
    elevation_offsets_m: list[float] = Field(default_factory=lambda: [-0.3, 0, 0.3])
    available_modalities: list[Literal["lidar", "thermal"]] = ["lidar", "thermal"]
    calibrated_fidelities: list[str] = Field(default_factory=lambda: ["L0", "L1"])
    calibrated_assets: list[str] = Field(default_factory=lambda: ["BW-01"])
    calibrated_range_m: tuple[Nonnegative, Positive] = (2, 4.5)
    minimum_registration_returns: int = Field(default=100, ge=6)
    minimum_incidence_cosine: Probability = 0.3
    maximum_vertical_spacing_m: Positive = 0.24
    restricted_assets: list[str] = Field(default_factory=list)
    priority_weights: dict[str, Nonnegative] = Field(
        default_factory=lambda: {
            "criticality": 0.15,
            "severity": 0.2,
            "deficiency": 0.3,
            "freshness": 0.15,
            "reinspection": 0.1,
            "failed_attempts": 0.1,
        }
    )
    utility_weights: dict[str, Nonnegative] = Field(
        default_factory=lambda: {
            "coverage": 0.25,
            "deficiency": 0.25,
            "risk": 0.2,
            "suitability": 0.15,
            "cost": 0.1,
            "redundancy": 0.05,
        }
    )

    @model_validator(mode="after")
    def valid(self):
        import numpy as np

        if (
            len(self.azimuths_rad)
            * len(self.elevation_offsets_m)
            * len(self.stand_off_shells_m)
            * len(self.available_modalities)
            > 200
        ):
            raise ValueError("Candidate pool exceeds configured safe limit")
        if not np.isfinite(
            [*self.start_world_m, *self.azimuths_rad, *self.elevation_offsets_m]
        ).all():
            raise ValueError("Finite geometry required")
        if (
            self.altitude_m[0] >= self.altitude_m[1]
            or self.calibrated_range_m[0] >= self.calibrated_range_m[1]
        ):
            raise ValueError("Invalid ordered limits")
        expected = {
            "criticality",
            "severity",
            "deficiency",
            "freshness",
            "reinspection",
            "failed_attempts",
        }
        if (
            set(self.priority_weights) != expected
            or abs(sum(self.priority_weights.values()) - 1) > 1e-8
        ):
            raise ValueError("Priority weights must sum to one with documented terms")
        if (
            set(self.utility_weights)
            != {"coverage", "deficiency", "risk", "suitability", "cost", "redundancy"}
            or abs(sum(self.utility_weights.values()) - 1) > 1e-8
        ):
            raise ValueError("Utility weights must sum to one")
        return self


class SurfaceCoverageEstimate(Contract):
    asset_id: ID
    reference_hash: str
    modeled_area_m2: Nonnegative
    observed_cells: list[int] = Field(default_factory=list)
    qualified_cells: list[int] = Field(default_factory=list)
    weak_cells: list[int] = Field(default_factory=list)
    finding_cells: list[int] = Field(default_factory=list)
    observed_area_m2: Nonnegative = 0
    qualified_area_m2: Nonnegative = 0
    acquired_at: UTC | None = None
    available_at: UTC | None = None
    source_ids: list[str] = Field(default_factory=list)
    registration_uncertainty_m: Nonnegative | None = None
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def subsets(self):
        if not set(self.qualified_cells) <= set(self.observed_cells):
            raise ValueError("Qualified cells must have actual observations")
        if (
            self.qualified_area_m2 > self.observed_area_m2 + 1e-6
            or self.observed_area_m2 > self.modeled_area_m2 + 1e-6
        ):
            raise ValueError("Coverage area exceeds modeled support")
        return self


class AssetPlanningState(Contract):
    asset_id: ID
    severity: Literal["green", "amber", "red", "unknown"] = "unknown"
    confidence: Probability = 0
    missing: list[str] = Field(default_factory=list)
    advisory_ids: list[str] = Field(default_factory=list)
    critical_process: bool = False
    reinspection: bool = False
    unsuccessful_attempts: int = Field(default=0, ge=0)
    thermal_image_only: bool = False


class BaselineInspectionSupport(Contract):
    capture_id: ID
    reference_hash: str
    reported_pose: Transform
    acquired_at: UTC
    available_at: UTC
    acquisition_parameters: dict[str, float | int]
    observed_cells: list[int] = Field(default_factory=list, max_length=200000)


class PlanningSnapshot(Contract):
    snapshot_id: ID
    at: UTC
    reference_hash: str
    assets: list[AssetPlanningState] = Field(min_length=1, max_length=100)
    coverage: list[SurfaceCoverageEstimate] = Field(default_factory=list, max_length=100)
    attempted_viewpoints: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    previous_plan_id: str | None = None
    baseline_support: BaselineInspectionSupport | None = None
    required_region_cells: dict[str, list[int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def causal(self):
        if self.at.tzinfo is None or any(
            c.acquired_at
            and (c.acquired_at.tzinfo is None or c.acquired_at > self.at)
            or c.available_at
            and (c.available_at.tzinfo is None or c.available_at > self.at)
            for c in self.coverage
        ):
            raise ValueError("Snapshot rejects future or naive observations")
        if self.baseline_support is not None and (
            self.baseline_support.acquired_at > self.at
            or self.baseline_support.available_at > self.at
            or self.baseline_support.reference_hash != self.reference_hash
        ):
            raise ValueError("Baseline support must be causal and reference-bound")
        if len({a.asset_id for a in self.assets}) != len(self.assets):
            raise ValueError("Duplicate assets")
        return self


class InspectionPlanningRequest(Contract):
    request_id: ID
    method: Literal["P0", "P1", "P2", "P3", "P3v2"] = "P3"
    budget_views: int = Field(default=4, ge=1, le=12)
    budget_s: Positive = 120
    maximum_travel_m: Positive = 50
    per_asset_limit: int = Field(default=4, ge=1, le=12)
    previous_plan_id: str | None = None


class AssetInspectionPriority(Contract):
    asset_id: ID
    score: Probability
    terms: dict[str, float]
    reasons: list[str]
    access: Literal["review_required", "restricted", "recommended"]


class ViewpointFeasibility(Contract):
    status: Literal["feasible", "infeasible", "requires_route_review"]
    reasons: list[str] = Field(default_factory=list)
    operator_review_required: bool = True


class ViewpointUtility(Contract):
    score: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] = 0
    terms: dict[str, float] = Field(default_factory=dict)
    new_cells: list[int] = Field(default_factory=list)


class CandidateViewpoint(Contract):
    viewpoint_id: ID
    asset_id: ID
    intended_region: str
    modality: Literal["lidar", "thermal"]
    planned_pose: Transform
    coordinate_frame: str = "plant-01"
    sensor_reference: str
    calibration_reference: str | None
    expected_range_m: Nonnegative
    incidence_cosine_mean: Probability
    predicted_visible_cells: list[int]
    predicted_usable_cells: list[int]
    expected_usable_area_m2: Nonnegative
    predicted_spacing_m: Nonnegative
    expected_quality: Probability
    registration_support_returns: int = Field(ge=0)
    acquisition_s: Positive
    feasibility: ViewpointFeasibility
    utility: ViewpointUtility = Field(default_factory=ViewpointUtility)
    assumptions: list[str]


class InspectionPlanStep(Contract):
    order: int = Field(ge=1)
    viewpoint_id: ID
    asset_id: ID
    travel_m: Nonnegative
    travel_s: Nonnegative
    acquisition_s: Positive
    marginal_area_m2: Nonnegative
    utility: ViewpointUtility


class PlanningExplanation(Contract):
    selected: list[str]
    rejected: dict[str, list[str]]
    limitations: list[str]
    recommended_actions: list[str]


class InspectionPlan(Contract):
    plan_id: ID
    version: int = 1
    at: UTC
    snapshot_hash: str
    policy_hash: str
    request: InspectionPlanningRequest
    priorities: list[AssetInspectionPriority]
    candidates: list[CandidateViewpoint]
    steps: list[InspectionPlanStep]
    estimated_duration_s: Nonnegative
    estimated_travel_m: Nonnegative
    expected_new_usable_area_m2: Nonnegative
    expected_deficiency_reduction: Probability
    targeted_assets: list[str]
    relevant_advisories: list[str]
    status: Literal[
        "recommended", "no_viable_viewpoint", "continue_monitoring", "requires_route_review"
    ]
    approval_status: Literal["pending_operator_review"] = "pending_operator_review"
    explanation: PlanningExplanation
    optimization_runtime_s: Nonnegative
    previous_plan_id: str | None = None


class ReinspectionRecommendation(Contract):
    previous_plan_id: ID
    snapshot_hash: str
    outcome: Literal["replan", "manual_review_required", "continue_monitoring"]
    reasons: list[str]


class PlanningEvaluationRecord(Contract):
    trial_id: ID
    method: Literal["P0", "P1", "P2", "P3", "P3v2"]
    partition: Literal["development", "heldout"]
    plan_hash: str
    metrics: dict[str, float | int | None]
    limitations: list[str]
