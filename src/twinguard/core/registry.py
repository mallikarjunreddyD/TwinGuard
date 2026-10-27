from pathlib import Path
import json
from twinguard.core import contracts
from twinguard.evaluation.contracts import (
    FaultInjection,
    ExperimentDefinition,
    ExperimentRun,
    GroundTruthSnapshot,
)
from twinguard.plant.config import PlantConfig
from twinguard.plant.contracts import SimulationManifest

from twinguard.core.observations import ObservationManifest
from twinguard.sensing.config import AcquisitionConfig

PUBLIC_MODELS = {
    name: getattr(contracts, name)
    for name in (
        "SensorConfiguration",
        "Artifact",
        "Asset",
        "PlantState",
        "SensorObservation",
        "InspectionCapture",
        "GeometricDetection",
        "EvidenceRecord",
        "ConditionAssessment",
        "DatasetProvenance",
    )
}
PUBLIC_MODELS["ObservationManifest"] = ObservationManifest
CONFIG_MODELS = {
    "AcquisitionConfig": AcquisitionConfig,
    "PlantConfig": PlantConfig,
    "SimulationManifest": SimulationManifest,
    "ScenarioDefinition": contracts.ScenarioDefinition,
    "ExperimentDefinition": ExperimentDefinition,
    "ExperimentRun": ExperimentRun,
}
RESTRICTED_MODELS = {"FaultInjection": FaultInjection, "GroundTruthSnapshot": GroundTruthSnapshot}
ALL_MODELS = PUBLIC_MODELS | CONFIG_MODELS | RESTRICTED_MODELS


def export_schemas(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    for name, model in ALL_MODELS.items():
        directory = destination / "restricted" if name in RESTRICTED_MODELS else destination
        directory.mkdir(exist_ok=True)
        (directory / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2) + "\n"
        )
