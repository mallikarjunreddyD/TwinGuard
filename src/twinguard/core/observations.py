"""Public-only observation manifests/loaders. No simulator or evaluator imports."""

from pathlib import Path
from typing import Literal
import hashlib
import numpy as np
from pydantic import Field
from .contracts import (
    Contract,
    ID,
    Artifact,
    DatasetProvenance,
    InspectionCapture,
    SensorObservation,
)


class ObservationReference(Contract):
    observation_id: ID
    record_uri: str
    kind: Literal["InspectionCapture", "SensorObservation"]


class ObservationManifest(Contract):
    manifest_id: ID
    run_id: ID
    dataset: DatasetProvenance
    software_version: ID
    configuration_version: ID
    master_seed: int = Field(ge=0)
    acquisition_namespace: ID
    observations: list[ObservationReference]
    artifacts: list[Artifact]


def public_path(root: Path, uri: str) -> Path:
    relative = Path(uri)
    if relative.is_absolute() or not relative.parts or relative.parts[0] != "observations":
        raise ValueError("Public data must be under observations/")
    path = (root / relative).resolve()
    if not path.is_relative_to((root / "observations").resolve()) or not path.is_relative_to(
        root.resolve() / "observations"
    ):
        raise ValueError("Public reference escapes observation storage")
    return path


def validate_import_manifest(root: Path, verify_checksums: bool = True) -> ObservationManifest:
    manifest = ObservationManifest.model_validate_json((root / "manifest.json").read_text())
    for artifact in manifest.artifacts:
        path = public_path(root, artifact.uri)
        if not path.is_file():
            raise ValueError(f"Missing observation artifact: {artifact.uri}")
        if (
            verify_checksums
            and artifact.sha256
            and hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256
        ):
            raise ValueError(f"Observation checksum mismatch: {artifact.uri}")
    for reference in manifest.observations:
        public_path(root, reference.record_uri)
    return manifest


def load_public_observations(root: Path):
    manifest = validate_import_manifest(root)
    records: list[InspectionCapture | SensorObservation] = []
    for reference in manifest.observations:
        path = public_path(root, reference.record_uri)
        model = InspectionCapture if reference.kind == "InspectionCapture" else SensorObservation
        lines = path.read_text().splitlines() if path.suffix == ".jsonl" else [path.read_text()]
        records.extend(model.model_validate_json(line) for line in lines if line.strip())
    return records


def load_capture_arrays(root: Path, record: InspectionCapture):
    path = public_path(root, record.artifact.uri)
    if path.suffix == ".ply" and record.modality == "lidar":
        import trimesh

        cloud = trimesh.load(path, process=False)
        if not isinstance(cloud, trimesh.points.PointCloud):
            raise ValueError("Observation must be a point cloud, not a hidden mesh")
        arrays = {"points_m": np.asarray(cloud.vertices)}
    else:
        with np.load(path, allow_pickle=False) as data:
            arrays = {k: data[k].copy() for k in data.files}
    allowed = (
        {"points_m", "valid_returns"}
        if record.modality == "lidar"
        else {"temperature_c", "valid_mask", "saturation_mask", "pixel_status"}
    )
    if not set(arrays) <= allowed:
        raise ValueError("Unexpected or privileged arrays in public artifact")
    if record.modality == "lidar":
        points = arrays["points_m"]
        if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
            raise ValueError("Invalid measured points")
        if "valid_returns" in arrays and (
            arrays["valid_returns"].ndim != 1
            or arrays["valid_returns"].dtype != np.bool_
            or arrays["valid_returns"].sum() != len(points)
        ):
            raise ValueError("Invalid LiDAR return mask")
    else:
        temperature = arrays["temperature_c"]
        mask = arrays["valid_mask"]
        if (
            temperature.ndim != 2
            or temperature.shape != mask.shape
            or mask.dtype != np.bool_
            or not np.isfinite(temperature[mask]).all()
            or np.any(temperature[mask] < -273.15)
            or not np.isnan(temperature[~mask]).all()
        ):
            raise ValueError("Invalid thermal array/mask")
        if "saturation_mask" in arrays:
            saturated = arrays["saturation_mask"]
            if (
                saturated.shape != mask.shape
                or saturated.dtype != np.bool_
                or np.any(saturated & ~mask)
            ):
                raise ValueError("Invalid saturation mask")
        if "pixel_status" in arrays:
            status = arrays["pixel_status"]
            if (
                status.shape != mask.shape
                or not np.isin(status, [0, 1, 2, 3]).all()
                or not np.array_equal(np.isin(status, [1, 3]), mask)
            ):
                raise ValueError("Invalid thermal pixel classification")
            if "saturation_mask" not in arrays or not np.array_equal(
                status == 3, arrays["saturation_mask"]
            ):
                raise ValueError("Saturation/status mismatch")
    return arrays
