"""Allowlisted analytics boundary; unknown fields fail closed at every nested model."""

import json
from pathlib import Path
from .contracts import SensorObservation, InspectionCapture

PUBLIC_OBSERVATIONS = (SensorObservation, InspectionCapture)


def analytics_json(record: SensorObservation | InspectionCapture) -> str:
    if type(record) not in PUBLIC_OBSERVATIONS:
        raise TypeError("Only public observations may cross analytics boundary")
    validated = type(record).model_validate(record.model_dump())
    return validated.model_dump_json()


def write_observation(record: SensorObservation | InspectionCapture, path: Path) -> None:
    path.write_text(analytics_json(record) + "\n")


def write_ground_truth(record, root: Path) -> Path:
    from twinguard.evaluation.contracts import FaultInjection
    import os

    if type(record) is not FaultInjection:
        raise TypeError("Expected restricted FaultInjection")
    record = FaultInjection.model_validate(record.model_dump())
    directory = root / "datasets" / "ground_truth"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    path = directory / f"{record.fault_id}.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(record.model_dump(mode="json"), stream, indent=2)
    return path
