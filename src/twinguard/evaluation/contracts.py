"""Restricted simulation/evaluation contracts. Never import into analytics ingestion."""

from typing import Annotated, Literal, Protocol
from pydantic import Field, model_validator
from twinguard.core.contracts import Contract, ID, Number, Artifact
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

    @model_validator(mode="after")
    def interval(self):
        if self.end_at <= self.start_at:
            raise ValueError("Fault end must follow start")
        if self.true_process_deviation is not None and not self.deviation_unit:
            raise ValueError("Process deviation requires unit")
        return self


class ExperimentDefinition(Contract):
    experiment_id: Literal["E1", "E2", "E3", "E4"]
    version: ID
    inputs: list[str]
    outputs: list[str]
    planned_metrics: list[str]
    baseline: str
    implementation_status: Literal["not_implemented"] = "not_implemented"


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
