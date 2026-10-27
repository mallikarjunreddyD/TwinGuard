"""Privileged acquisition orchestration, separate from public observation loading."""

from pathlib import Path
import json
import time
import yaml
from twinguard.core.contracts import ID
from pydantic import TypeAdapter
from .config import AcquisitionConfig
from .noise import stream
from .lidar import LidarSensor
from .thermal import ThermalSensor
from .iot import generate_iot
from .export import export_capture, export_iot, write_manifest, dataset_identity


def time_token(t):
    import numpy as np

    return "t_" + np.format_float_positional(float(t), unique=True, trim="-").replace(
        "-", "minus_"
    ).replace(".", "p")


def load_installation(path: Path):
    return AcquisitionConfig.model_validate(yaml.safe_load(path.read_text()))


def acquire(
    reader,
    scenario,
    installation: AcquisitionConfig,
    output: Path,
    modality="all",
    time_s=None,
    execution_order=None,
):
    TypeAdapter(ID).validate_python(output.name)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose a new empty acquisition output directory")
    configured = {installation.lidar.sensor_id, installation.thermal.sensor_id} | {
        c.sensor_id for c in installation.iot
    }
    if not set(scenario.sensor_config_ids) <= configured:
        raise ValueError("Scenario references unconfigured sensor")
    if any(
        c.asset_id not in scenario.asset_ids
        for c in [installation.lidar, installation.thermal] + installation.iot
    ):
        raise ValueError("Sensor references missing scenario asset")
    output.mkdir(parents=True, exist_ok=True)
    private = output / "evaluation_private"
    private.mkdir(mode=0o700)
    (private / "installation.json").write_text(installation.model_dump_json(indent=2))
    (private / "installation.json").chmod(0o600)
    (private / "scenario.json").write_text(scenario.model_dump_json(indent=2))
    (private / "scenario.json").chmod(0o600)
    event_list = []
    if modality in ("lidar", "thermal"):
        config = installation.lidar if modality == "lidar" else installation.thermal
        event_list = [(config.sensor_id, modality, float(time_s))]
    elif modality == "all":
        event_list = [(e.sensor_id, e.modality, e.offset_s) for e in scenario.inspections]
    elif modality != "iot":
        raise ValueError("Unsupported acquisition modality")
    if execution_order is not None:
        event_list.sort(key=lambda event: execution_order.index(event[1]))
    provenance_id = dataset_identity(scenario.scenario_id, scenario.random_seed, installation)
    records = []
    timings = {}
    for sensor_id, kind, t in event_list:
        config = installation.lidar if kind == "lidar" else installation.thermal
        if kind not in ("lidar", "thermal") or sensor_id != config.sensor_id:
            raise ValueError("Unsupported scheduled sensor")
        event_key = f"{sensor_id}-{time_token(t)}"
        event = scenario.scenario_id + "-" + event_key
        pose = installation.event_poses.get(event_key, config.pose)
        physical = reader.read_at(t)
        instrument = (
            LidarSensor(installation.lidar)
            if kind == "lidar"
            else ThermalSensor(installation.thermal)
        )
        started = time.perf_counter()
        product = instrument.capture(
            physical,
            event,
            provenance_id,
            stream(scenario.random_seed, scenario.scenario_id, sensor_id, event),
            stream(scenario.random_seed, scenario.scenario_id, sensor_id, event, "pose"),
            pose,
        )
        timings[event] = time.perf_counter() - started
        records.append(export_capture(output, product))
    from .export import private_npz
    import numpy as np

    context = reader.read_at(event_list[0][2] if event_list else 0)
    private_npz(
        private / "coverage_geometry.npz",
        {
            "vertices_world_m": np.concatenate(
                [surface.vertices_world_m for surface in context.surfaces]
            )
        },
    )
    has_iot = modality in ("all", "iot")
    if has_iot:
        started = time.perf_counter()
        product = generate_iot(
            reader,
            [
                sensor
                for sensor in installation.iot
                if sensor.sensor_id in scenario.sensor_config_ids
            ],
            scenario.duration_s,
            scenario.random_seed,
            scenario.scenario_id,
            provenance_id,
        )
        export_iot(output, product)
        timings["iot"] = time.perf_counter() - started
    manifest = write_manifest(
        output, scenario.scenario_id, scenario.random_seed, installation, records, has_iot
    )
    (private / "acquisition_runtime.json").write_text(json.dumps(timings, indent=2))
    (private / "acquisition_runtime.json").chmod(0o600)
    import resource

    resource_path = private / "resource.json"
    resource_path.write_text(
        json.dumps(
            {
                "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                "scope": "Linux process peak RSS including interpreter/backend/plant/acquisition",
            },
            indent=2,
        )
    )
    resource_path.chmod(0o600)
    return manifest
