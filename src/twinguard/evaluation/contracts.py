"""Restricted simulation/evaluation contracts. Never import into analytics ingestion."""

from typing import Annotated, Literal, Protocol
from pydantic import Field, model_validator
from twinguard.core.contracts import Contract, ID, Number, Nonnegative, Artifact
from twinguard.core.time import UTC


class FaultInjection(Contract):
    fault_id: ID
    asset_id: ID
    category: Literal[
        "localized_geometric_deformation",
        "structural_support_displacement",
        "thermal_hotspot",
        "abnormal_process_measurement",
    ]
    start_at: UTC
    end_at: UTC
    severity_parameters: dict[str, Number]
    affected_region_id: ID
    true_displacement_m: Number | None = None
    true_process_deviation: Number | None = None
    deviation_unit: str | None = None
    ground_truth_artifacts: list[Artifact]

    center_local_m: tuple[Number, Number, Number] = (0, 0, 1.2)
    extent_m: tuple[Nonnegative, Nonnegative, Nonnegative] = (0.4, 0.1, 0.5)
    direction: tuple[Number, Number, Number] = (0, 1, 0)
    displacement_vector_m: tuple[Number, Number, Number] | None = None
    evolution: Literal["step", "linear"] = "step"
    growth_duration_s: Nonnegative = 0
    persistence: Literal["persistent", "recover"] | None = None
    recovery_duration_s: Nonnegative = 0
    repair_at: UTC | None = None
    process_variable: Literal["pressure_pa", "temperature_c"] = "pressure_pa"
    target_value: Number | None = None

    @model_validator(mode="after")
    def interval(self):
        if self.end_at <= self.start_at:
            raise ValueError("Fault end must follow start")
        if self.true_process_deviation is not None and not self.deviation_unit:
            raise ValueError("Process deviation requires unit")
        if any(x <= 0 for x in self.extent_m):
            raise ValueError("Fault extents must be positive")
        if sum(x * x for x in self.direction) == 0:
            raise ValueError("Fault direction must be nonzero")
        if self.growth_duration_s > (self.end_at - self.start_at).total_seconds():
            raise ValueError("Growth interval exceeds injection interval")
        if self.evolution == "linear" and self.growth_duration_s == 0:
            raise ValueError("Linear evolution requires positive growth duration")
        if self.repair_at is not None and self.repair_at < self.start_at:
            raise ValueError("Repair precedes initiation")
        return self


class ExperimentDefinition(Contract):
    experiment_id: Literal["E1", "E2", "E3", "E4", "E5"]
    version: ID
    inputs: list[str]
    outputs: list[str]
    planned_metrics: list[str]
    baseline: str
    benchmark_reference: str | None = None
    implementation_status: Literal["not_implemented", "in_progress", "implemented", "validated"] = (
        "not_implemented"
    )


class ExperimentRun(Contract):
    experiment_id: ID
    run_id: ID
    scenario_id: ID
    dataset_id: ID
    dataset_provenance_reference: ID
    dataset_source_type: Literal[
        "synthetic", "public_real_world", "hybrid", "physical_experimental"
    ]
    random_seed: Annotated[int, Field(ge=0)]
    software_version: ID
    git_commit: str | None = None
    configuration_version: ID
    algorithm_references: list[ID]
    configuration_references: list[ID]
    started_at: UTC
    ended_at: UTC | None = None
    outputs: list[Artifact]
    evaluation_status: Literal["pending", "not_implemented", "completed", "failed"]
    metric_artifacts: list[Artifact]
    implementation_status: Literal["not_implemented", "in_progress", "implemented", "validated"] = (
        "not_implemented"
    )
    run_outcome: Literal["pending", "passed", "failed", "error"] = "pending"
    test_result_artifacts: list[Artifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered(self):
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("Run end precedes start")
        if self.evaluation_status == "completed" and (
            self.ended_at is None or not self.metric_artifacts
        ):
            raise ValueError("Completed evaluation requires end and metric evidence")
        return self


class Evaluator(Protocol):
    def evaluate(self, run: ExperimentRun, truth: list[FaultInjection]) -> ExperimentRun:
        """Future evaluator must compute metrics; Phase 0 provides no implementation."""
        ...


def artifact_path(experiment_id: str, run_id: str, artifact_id: str) -> str:
    from pydantic import TypeAdapter

    for identifier in (experiment_id, run_id, artifact_id):
        TypeAdapter(ID).validate_python(identifier)
    return f"experiments/outputs/{experiment_id}/{run_id}/{artifact_id}"


class FaultState(Contract):
    fault_id: ID
    asset_id: ID
    category: str
    factor: Annotated[float, Field(ge=0, le=1)]
    present: bool
    configuration: FaultInjection
    applied_peak_displacement_m: Nonnegative | None = None
    applied_translation_m: tuple[Number, Number, Number] | None = None
    applied_peak_temperature_delta_c: Number | None = None
    actual_process_value: Number | None = None


class GroundTruthSnapshot(Contract):
    truth_id: ID
    run_id: ID
    scenario_id: ID
    timestamp: UTC
    time_s: Number
    fault_states: list[FaultState]


class ExperimentBenchmark(Contract):
    benchmark_id: ID
    experiment_id: Literal["E1", "E2"]
    analytics_config: str
    accepted_reference: str
    calibration_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    evaluation_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    fidelities: list[Literal["L0", "L1", "L2"]] = Field(default=["L1"])
    amplitudes_m: list[Nonnegative] = Field(default_factory=lambda: [0.0])
    viewpoints: list[Literal["same", "changed"]] = Field(default=["changed"])
    robustness_viewpoints: list[Literal["partial", "high_pose", "low_overlap"]] = Field(
        default_factory=list
    )
    include_support: bool = False

    @model_validator(mode="after")
    def split(self):
        if set(self.calibration_seeds) & set(self.evaluation_seeds):
            raise ValueError("Calibration/evaluation seeds must be disjoint")
        return self


class FusionBenchmark(Contract):
    experiment_id: Literal["E3"]
    version: ID
    policy: str
    controlled_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    end_to_end_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    development_controlled_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    development_end_to_end_seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    operating_model: str
    thermal_model_directory: str
    geometric_calibration: str
    original_geometry_calibration: str
    historical_geometry: str
    assessment_step_s: int = Field(default=5, ge=1, le=125)
    workers: int = Field(default=3, ge=1, le=4)
    event_matching: str
    availability_assumptions: str

    @model_validator(mode="after")
    def disjoint(self):
        partitions = [
            self.controlled_seeds,
            self.end_to_end_seeds,
            self.development_controlled_seeds,
            self.development_end_to_end_seeds,
        ]
        if any(len(v) != len(set(v)) for v in partitions) or any(
            set(a) & set(b) for i, a in enumerate(partitions) for b in partitions[i + 1 :]
        ):
            raise ValueError("Fusion development/evaluation seeds must be unique and disjoint")
        return self
