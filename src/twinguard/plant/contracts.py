"""Simulation management contracts; explicitly excluded from analytics serialization."""

from typing import Literal
from pydantic import Field
from twinguard.core.contracts import Contract, ID, Artifact, Nonnegative, Number, DatasetProvenance
from twinguard.core.time import UTC


class RunArtifact(Artifact):
    size_bytes: int = Field(ge=0)


class SimulationManifest(Contract):
    run_id: ID
    scenario_id: ID
    scenario_version: ID
    random_seed: int = Field(ge=0)
    software_version: ID
    git_commit: str | None
    working_tree_dirty: bool
    configuration_version: ID
    model_version: ID
    configuration_reference: str
    controller_configuration_reference: str
    provenance: DatasetProvenance
    started_at: UTC
    ended_at: UTC
    generation_runtime_s: Nonnegative
    snapshot_times_s: list[Number]
    artifact_class: Literal[
        "simulation physical state; not sensor observations or analytics output"
    ]
    source_tree_sha256: str | None = None
    artifacts: list[RunArtifact]
