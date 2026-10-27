"""Explicit allowlisted observation export; restricted simulation diagnostics stay separate."""

from pathlib import Path
import csv
import hashlib
import json
import numpy as np
import trimesh
from twinguard.core.contracts import (
    Artifact,
    InspectionCapture,
    DatasetProvenance,
    SensorConfiguration,
)
from twinguard.core.observations import ObservationManifest, ObservationReference
from twinguard.core.serialization import analytics_json
from twinguard import __version__
from .config import AcquisitionConfig

PUBLIC_KEYS = {
    "lidar": {"points_m", "valid_returns"},
    "thermal": {"temperature_c", "valid_mask", "saturation_mask", "pixel_status"},
}


def artifact(root, path):
    relative = str(path.relative_to(root))
    return Artifact(
        artifact_id="artifact-" + hashlib.sha256(relative.encode()).hexdigest()[:24],
        uri=relative,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def private_npz(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    np.savez_compressed(path, **{k: np.asarray(v) for k, v in data.items()})
    path.chmod(0o600)


def export_capture(root: Path, product):
    record = InspectionCapture.model_validate_json(analytics_json(product.observation))
    if set(product.arrays) != PUBLIC_KEYS[record.modality]:
        raise ValueError("Unexpected arrays in public capture")
    folder = root / "observations" / record.modality
    folder.mkdir(parents=True, exist_ok=True)
    payload = folder / f"{record.capture_id}.npz"
    np.savez_compressed(payload, **product.arrays)
    record.artifact = artifact(root, payload)
    if record.modality == "lidar":
        trimesh.points.PointCloud(product.arrays["points_m"]).export(
            folder / f"{record.capture_id}.ply"
        )
    else:
        np.save(
            folder / f"{record.capture_id}.npy", product.arrays["temperature_c"], allow_pickle=False
        )
    metadata = folder / f"{record.capture_id}.json"
    metadata.write_text(analytics_json(record) + "\n")
    private_npz(
        root / "evaluation_private" / f"{record.capture_id}.npz", product.evaluation_private
    )
    return record


def export_iot(root, product):
    folder = root / "observations/iot"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "observations.jsonl").write_text(
        "".join(analytics_json(r) + "\n" for r in product.observations)
    )
    fields = [
        "observation_id",
        "sensor_id",
        "asset_id",
        "acquired_at",
        "received_at",
        "sequence_number",
        "measurement_type",
        "value",
        "unit",
        "uncertainty",
        "quality",
        "delivery_status",
        "provenance_id",
        "schema_version",
        "configuration_version",
        "source_type",
    ]
    with (folder / "observations.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in product.observations:
            data = record.model_dump(mode="json")
            writer.writerow({key: data[key] for key in fields})
    private = root / "evaluation_private"
    private.mkdir(exist_ok=True, mode=0o700)
    private.chmod(0o700)
    path = private / "sensor_truth.json"
    path.write_text(json.dumps(product.evaluation_private, indent=2, allow_nan=False) + "\n")
    path.chmod(0o600)


def dataset_identity(scenario_id, seed, installation):
    canonical = AcquisitionConfig.model_validate(installation.model_dump(mode="json"))
    payload = json.dumps(
        [scenario_id, seed, canonical.model_dump(mode="json")],
        sort_keys=True,
        separators=(",", ":"),
    )
    return "observations-" + scenario_id + "-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def write_manifest(root, scenario_id, seed, installation, records, has_iot):
    refs = [
        ObservationReference(
            observation_id=r.capture_id,
            record_uri=f"observations/{r.modality}/{r.capture_id}.json",
            kind="InspectionCapture",
        )
        for r in records
    ]
    if has_iot:
        refs.append(
            ObservationReference(
                observation_id="iot-stream",
                record_uri="observations/iot/observations.jsonl",
                kind="SensorObservation",
            )
        )
    descriptors = []
    units = {
        "pressure": "Pa",
        "load": "1",
        "vibration": "m/s2",
        "surface_temperature": "degC",
        "process_temperature": "degC",
    }
    for c in installation.iot:
        measurements = {
            "measurement_source": c.source,
            "sampling_interval_s": c.sampling_interval_s,
            "unit": units[c.source],
            "measurement_std": c.noise.sigma,
        }
        if c.location_world_m is not None:
            measurements.update(
                dict(zip(("location_x_m", "location_y_m", "location_z_m"), c.location_world_m))
            )
        descriptors.append(
            SensorConfiguration(
                sensor_id=c.sensor_id,
                asset_id=c.asset_id,
                source_type="synthetic",
                configuration_version=c.configuration_version,
                description="Known fixed installation metadata; no noiseless measurements",
                modality="iot",
                calibration_reference=c.calibration_reference,
                measurement_configuration=measurements,
            ).model_dump(mode="json")
        )
    (root / "observations/sensor_installation.json").write_text(
        json.dumps(descriptors, indent=2) + "\n"
    )
    files = [artifact(root, p) for p in sorted((root / "observations").rglob("*")) if p.is_file()]
    dataset = DatasetProvenance(
        dataset_id=dataset_identity(scenario_id, seed, installation),
        source_type="synthetic",
        description="Virtual sensor measurements from a common simulated physical plant; no physical sensor calibration or fault-detection claims",
        artifacts=files,
    )
    manifest = ObservationManifest(
        manifest_id="manifest-" + root.name,
        run_id=root.name,
        dataset=dataset,
        software_version=__version__,
        configuration_version=installation.configuration_version,
        master_seed=seed,
        acquisition_namespace=scenario_id,
        observations=refs,
        artifacts=files,
    )
    (root / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest
