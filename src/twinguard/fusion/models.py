"""Versioned public fusion contracts; no simulator knowledge or probability claims."""

from typing import Literal
from pydantic import Field, model_validator
from twinguard.core.contracts import Contract, ID, Number, Nonnegative, ConditionAssessment
from twinguard.core.time import UTC


class ProcessingRecord(Contract):
    source_id: ID
    received_at: UTC
    available_at: UTC
    processed_at: UTC
    basis: Literal["recorded", "simulated_replay"]
    rationale: str = Field(min_length=1)
    clock_quality: Literal["synchronized", "uncertain", "unknown"] = "unknown"
    clock_uncertainty_s: Nonnegative = 0

    @model_validator(mode="after")
    def ordering(self):
        if self.processed_at < self.received_at or self.available_at < self.processed_at:
            raise ValueError("Analysis availability must follow receipt and processing")
        return self


class FusionEvidence(Contract):
    evidence_id: ID
    source_id: ID
    modality: Literal["fixed_sensor", "geometric", "thermal"]
    algorithm: ID
    algorithm_version: ID
    provenance_id: ID
    asset_id: ID | None
    sensor_id: ID | None = None
    capture_ids: list[ID] = Field(default_factory=list)
    model_id: ID | None = None
    acquired_at: UTC
    received_at: UTC
    available_at: UTC
    processed_at: UTC
    availability_basis: Literal["recorded", "simulated_replay"]
    clock_quality: Literal["synchronized", "uncertain", "unknown"]
    clock_uncertainty_s: Nonnegative = 0
    hypothesis: ID
    finding: Literal["positive", "negative", "inconclusive", "invalid", "unavailable"]
    value: Number | None = None
    observed_value: Number | None = None
    estimated_reference: Number | None = None
    residual: Number | None = None
    unit: str | None = None
    uncertainty_score: Nonnegative | None = None
    scope: ID
    measurement_basis: str
    qualification_status: str
    association: Literal["associated", "image_only", "ambiguous", "unknown"]
    region_id: ID | None = None
    bounds_world_m: tuple[tuple[Number, Number, Number], tuple[Number, Number, Number]] | None = (
        None
    )
    image_bounds: tuple[int, int, int, int] | None = None
    spatial_reference: ID | None = None
    region_comparison_possible: bool = False
    spatial_uncertainty_m: Nonnegative = 0
    origin_identity: ID
    dependence_group: ID
    derived_from: list[ID] = Field(default_factory=list)
    shared_references: list[ID] = Field(default_factory=list)
    quality: Literal["good", "degraded", "unknown", "invalid"]
    calibration_valid: bool = False
    registration_valid: bool | None = None
    coverage_status: str
    quality_indicators: dict[str, Number | str | bool] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    reinspection_candidate: bool = False
    authoritative_limit: bool = False
    recovery_eligible: bool = True

    @model_validator(mode="after")
    def consistency(self):
        if not self.acquired_at <= self.received_at <= self.processed_at <= self.available_at:
            raise ValueError("Acquisition/receipt/processing/availability order invalid")
        if self.finding in ["positive", "negative"] and (
            self.quality != "good"
            or not self.calibration_valid
            or self.qualification_status != "valid"
        ):
            raise ValueError("Qualified finding requires good calibrated valid evidence")
        if (
            self.modality == "geometric"
            and self.finding in ["positive", "negative"]
            and self.registration_valid is not True
        ):
            raise ValueError("Geometric finding requires valid registration")
        if self.region_comparison_possible and (
            self.association != "associated"
            or self.bounds_world_m is None
            or self.spatial_reference is None
        ):
            raise ValueError("Physical comparison needs associated bounds and frame")
        if self.bounds_world_m and any(a > b for a, b in zip(*self.bounds_world_m)):
            raise ValueError("Inverted spatial bounds")
        return self


class TemporalDecision(Contract):
    evidence_id: ID
    hazard_id: ID
    age_s: Number
    status: Literal[
        "current",
        "stale",
        "not_available",
        "future",
        "clock_unknown",
        "invalid",
        "inconclusive",
        "historical_repaired",
        "superseded",
    ]
    applicable: bool
    historical_context: bool
    reason: str


class CompatibilityDecision(Contract):
    evidence_ids: list[ID]
    dimension: Literal["spatial", "temporal", "dependence"]
    status: Literal[
        "compatible",
        "partially_compatible",
        "incompatible",
        "unknown",
        "dependent",
        "independent",
        "duplicate",
        "superseded",
    ]
    reason: str


class HazardRule(Contract):
    hazard_id: ID
    hypotheses: list[ID] = Field(min_length=1)
    asset_types: list[ID] = Field(min_length=1)
    modalities: list[Literal["fixed_sensor", "geometric", "thermal"]] = Field(min_length=1)
    max_age_s: Nonnegative
    coincidence_s: Nonnegative = 30
    spatial_requirement: Literal["none", "asset", "region"] = "asset"
    min_independent: int = Field(default=1, ge=1)
    required_scope: ID | None = None
    severity: Literal["amber", "red"] = "amber"
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    critical_limit_only: bool = False
    immediate: bool = False
    min_positive_count: int = Field(default=1, ge=1)
    min_duration_s: Nonnegative = 0
    automatic_recovery: bool = True
    recovery_count: int = Field(default=2, ge=1)
    recovery_duration_s: Nonnegative = 5
    clear_on_repair: bool = False
    manual_resolution: bool = True
    aggregation_window_s: Nonnegative = 300
    require_distinct_modalities: bool = False


class SensorAuthority(Contract):
    sensor_id: ID
    asset_id: ID
    measurement_type: str
    unit: str
    calibration_status: Literal["verified", "assumed_simulation", "unknown", "expired"]
    measurement_min: Number
    measurement_max: Number
    critical_limit: Number | None = None
    hysteresis: Nonnegative = 0
    engineering_basis: str | None = None

    @model_validator(mode="after")
    def limits(self):
        if self.measurement_min >= self.measurement_max:
            raise ValueError("Invalid instrument range")
        if self.critical_limit is not None and (
            not self.engineering_basis
            or not self.measurement_min < self.critical_limit <= self.measurement_max
        ):
            raise ValueError("Critical limit requires explicit basis and valid instrument range")
        return self


class MonitoringRequirement(Contract):
    requirement_id: ID
    asset_id: ID
    hypothesis: ID
    scope: ID
    max_age_s: Nonnegative
    sensor_id: ID | None = None


class FusionPolicy(Contract):
    policy_id: ID
    version: ID
    deployment_mode: Literal["illustrative_simulation", "site_review_required"]
    rationale: str
    assets: dict[ID, ID]
    authorities: list[SensorAuthority]
    requirements: list[MonitoringRequirement]
    rules: list[HazardRule]
    algorithm_preference: list[ID] = Field(
        default_factory=lambda: ["multiscale_calibrated", "patch_screening", "nearest_neighbor"]
    )
    dependence_groups: dict[str, ID] = Field(default_factory=dict)
    shared_reference_dependence: bool = True
    missing_monitoring_advisory: bool = True
    max_clock_uncertainty_s: Nonnegative = 1
    spatial_tolerance_m: Nonnegative = 0.05

    @model_validator(mode="after")
    def unique(self):
        for values in [
            [a.sensor_id for a in self.authorities],
            [r.hazard_id for r in self.rules],
            [r.requirement_id for r in self.requirements],
        ]:
            if len(values) != len(set(values)):
                raise ValueError("Duplicate policy identifiers")
        if any(a.asset_id not in self.assets for a in self.authorities) or any(
            r.asset_id not in self.assets for r in self.requirements
        ):
            raise ValueError("Unknown policy asset")
        for rule in self.rules:
            if any(kind not in set(self.assets.values()) for kind in rule.asset_types):
                raise ValueError("Rule references an unknown asset type")
            if rule.require_distinct_modalities and rule.min_independent > len(
                set(rule.modalities)
            ):
                raise ValueError("Impossible distinct-modality requirement")
            if rule.severity == "red" and not rule.critical_limit_only and rule.min_independent < 2:
                raise ValueError("Single-source red requires the explicit authoritative limit path")
        return self


class OperatorAction(Contract):
    action_id: ID
    asset_id: ID
    hazard_id: ID | None = None
    at: UTC
    kind: Literal["acknowledge", "repair", "resolve"]
    rationale: str = Field(min_length=1)


class AdvisoryEvent(Contract):
    event_id: ID
    asset_id: ID
    hazard_id: ID
    severity: Literal["amber", "red"]
    lifecycle: Literal["candidate", "active", "escalated", "acknowledged", "resolved"]
    opened_at: UTC
    updated_at: UTC
    positive_ids: list[ID] = Field(default_factory=list)
    positive_origins: list[ID] = Field(default_factory=list)
    positive_times: list[UTC] = Field(default_factory=list)
    first_positive_at: UTC
    last_observation_at: UTC
    recovery_ids: list[ID] = Field(default_factory=list)
    recovery_times: list[UTC] = Field(default_factory=list)
    recovery_started_at: UTC | None = None
    recovery_last_at: UTC | None = None
    action: str
    monitoring_unavailable: bool = False


class AdvisoryNotice(Contract):
    notice_id: ID
    event_id: ID
    asset_id: ID
    at: UTC
    transition: str
    action: str
    transport_status: Literal["record_only"] = "record_only"


class DecisionTrace(Contract):
    assessment: ConditionAssessment
    method: Literal["F0", "F1"]
    policy_sha256: str
    triggered_hazards: list[ID]
    positive_ids: list[ID]
    historical_positive_ids: list[ID] = Field(default_factory=list)
    negative_ids: list[ID]
    missing_requirements: list[ID]
    rejected_ids: list[ID]
    temporal: list[TemporalDecision]
    compatibility: list[CompatibilityDecision]
    rationale: list[str]
    conflicts: list[str]
    event_ids: list[ID]
    replay_mode: Literal["online", "retrospective"]
    software_version: str


class FusionState(Contract):
    method: Literal["F0", "F1"] | None = None
    policy_sha256: str | None = None
    assessed_at: UTC | None = None
    evidence: dict[ID, FusionEvidence] = Field(default_factory=dict)
    events: dict[str, AdvisoryEvent] = Field(default_factory=dict)
    applied_actions: list[ID] = Field(default_factory=list)
    notices: list[AdvisoryNotice] = Field(default_factory=list)


class FusionEvidenceManifest(Contract):
    kind: Literal["FusionEvidenceManifest"] = "FusionEvidenceManifest"
    evidence_uri: str
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    count: int = Field(ge=0)
    provenance: dict[str, str | Number | bool | None] = Field(default_factory=dict)
