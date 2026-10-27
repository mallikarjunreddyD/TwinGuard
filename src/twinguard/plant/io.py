"""Privileged simulation artifacts; none of these files is an analytics observation."""

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import subprocess
import time
import numpy as np
import trimesh
import yaml
from pydantic import TypeAdapter
from twinguard import __version__
from twinguard.core.contracts import ID
from twinguard.core.config import load_scenario
from twinguard.core.contracts import ScenarioDefinition
from twinguard.evaluation.contracts import FaultInjection
from .config import load_plant_config, PlantConfig
from .model import create_baseline_plant
from .simulator import PlantSimulator
from .contracts import SimulationManifest
from .dynamics import operating_reference


def write_json(path, data, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if private:
        path.parent.chmod(0o700)
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    if private:
        path.chmod(0o600)


def time_name(t):
    return (
        ("t_" + np.format_float_positional(float(t), unique=True, trim="-"))
        .replace("-", "minus_")
        .replace(".", "p")
    )


def export_snapshot(snapshot, directory: Path, formats=("glb", "ply")):
    directory.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()
    metadata = []
    for aid, asset in snapshot.assets.items():
        # Each PLY is explicitly in world coordinates; GLB nodes retain asset IDs.
        mesh = trimesh.Trimesh(vertices=asset.vertices_world_m, faces=asset.faces, process=False)
        scene.add_geometry(mesh, geom_name=aid, node_name=aid)
        if "ply" in formats:
            mesh.export(directory / f"{aid}.ply")
        metadata.append(
            {
                "asset_id": aid,
                "coordinate_frame": {"kind": "world", "reference_id": snapshot.operating.plant_id},
                "T_world_asset": asset.world_pose.matrix,
                "normal_expansion_m": asset.normal_expansion_m,
                "structural_translation_m": asset.structural_translation_m.tolist(),
                "surface_temperature_min_c": float(asset.surface_temperature_c.min()),
                "surface_temperature_max_c": float(asset.surface_temperature_c.max()),
            }
        )
    if "glb" in formats:
        (directory / "plant.glb").write_bytes(scene.export(file_type="glb"))
    write_json(
        directory / "assets.json",
        {
            "schema_version": "1.0.0",
            "snapshot_id": time_name(snapshot.time_s),
            "timestamp": snapshot.timestamp.isoformat(),
            "model_version": snapshot.model_version,
            "configuration_version": snapshot.configuration_version,
            "assets": metadata,
        },
    )
    np.savez_compressed(
        directory / "fields.npz",
        **{f"{aid}_temperature_c": a.surface_temperature_c for aid, a in snapshot.assets.items()},
    )
    return directory


def simulator_from_scenario(path: Path, root: Path, config_path: Path | None = None):
    scenario = load_scenario(path, root)
    config = load_plant_config(config_path or root / "configs/plant.yaml")
    faults = [
        FaultInjection.model_validate(
            yaml.safe_load((root / "datasets/ground_truth" / f"{reference}.yaml").read_text())
        )
        for reference in scenario.fault_config_references
    ]
    return PlantSimulator(create_baseline_plant(config, scenario.random_seed), scenario, faults)


def trace_rows(simulator):
    rows = []
    config = simulator.baseline.config.dynamics
    for t in simulator.time_grid():
        operating = simulator.operating_at(float(t))
        _, temp, pressure, _ = operating_reference(
            simulator.scenario, config, float(t), simulator.scenario.random_seed
        )
        row = operating.model_dump(mode="json")
        row.update(time_s=float(t), reference_temperature_c=temp, reference_pressure_pa=pressure)
        rows.append(row)
    return rows


def refresh_checksums(directory):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"] = [
        {
            "artifact_id": "artifact-"
            + hashlib.sha256(str(p.relative_to(directory)).encode()).hexdigest()[:24],
            "uri": str(p.relative_to(directory)),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size_bytes": p.stat().st_size,
            "media_type": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
        }
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p != manifest_path
    ]
    write_json(manifest_path, SimulationManifest.model_validate(manifest))
    return manifest


def export_run(simulator: PlantSimulator, output: Path, snapshot_times=None):
    TypeAdapter(ID).validate_python(output.name)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty; choose a new run directory")
    output.mkdir(parents=True, exist_ok=True)
    begun = time.perf_counter()
    started = datetime.now(timezone.utc)
    private = output / "restricted"
    private.mkdir(mode=0o700)
    write_json(output / "plant_config.json", simulator.baseline.config)
    write_json(private / "scenario.json", simulator.scenario, True)
    write_json(
        private / "faults.json", [f.model_dump(mode="json") for f in simulator._faults], True
    )
    baseline_scene = simulator.baseline.scene()
    baseline_dir = output / "baseline"
    baseline_dir.mkdir()
    (baseline_dir / "plant.glb").write_bytes(baseline_scene.export(file_type="glb"))
    for aid in simulator.baseline.asset_registry:
        mesh = simulator.baseline.mesh(aid)
        mesh.apply_transform(simulator.baseline.world_pose(aid).matrix)
        mesh.export(baseline_dir / f"{aid}.ply")
    write_json(
        baseline_dir / "assets.json",
        [a.model_dump(mode="json") for a in simulator.baseline.asset_registry.values()],
    )
    write_json(output / "operating_states.json", trace_rows(simulator))
    times = sorted(
        set(
            snapshot_times
            if snapshot_times is not None
            else [0, min(60, simulator.scenario.duration_s), simulator.scenario.duration_s]
            + [i.offset_s for i in simulator.scenario.inspections]
        )
    )
    truth = []
    for t in times:
        export_snapshot(simulator.state_at(t), output / "snapshots" / time_name(t))
        record = simulator.ground_truth_at(t, output.name)
        truth.append(record.model_dump(mode="json"))
    write_json(private / "ground_truth.json", truth, True)
    timeline = [
        {
            "type": "inspection_schedule",
            "time_s": i.offset_s,
            "modality": i.modality,
            "sensor_id": i.sensor_id,
        }
        for i in simulator.scenario.inspections
    ]
    for fault in simulator._faults:
        timeline.append(
            {
                "type": "fault_initiation",
                "fault_id": fault.fault_id,
                "time_s": (fault.start_at - simulator.scenario.simulation_start).total_seconds(),
            }
        )
    write_json(private / "timeline.json", timeline, True)
    commit = (
        subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        or None
    )
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        ).stdout.strip()
    )
    manifest = {
        "schema_version": "1.0.0",
        "run_id": output.name,
        "scenario_id": simulator.scenario.scenario_id,
        "scenario_version": simulator.scenario.version,
        "random_seed": simulator.scenario.random_seed,
        "software_version": __version__,
        "git_commit": commit,
        "working_tree_dirty": dirty,
        "configuration_version": simulator.baseline.config.configuration_version,
        "model_version": simulator.baseline.config.model_version,
        "configuration_reference": "plant_config.json",
        "controller_configuration_reference": "restricted/scenario.json",
        "provenance": simulator.scenario.dataset.model_dump(mode="json"),
        "started_at": started.isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "generation_runtime_s": time.perf_counter() - begun,
        "snapshot_times_s": times,
        "artifact_class": "simulation physical state; not sensor observations or analytics output",
        "source_tree_sha256": source_digest(),
        "artifacts": [],
    }
    write_json(output / "manifest.json", manifest)
    (output / "SUMMARY.md").write_text(
        f"# {simulator.scenario.scenario_id} simulation ground truth\n\n{simulator.scenario.description}\n\nSeven-asset surrogate; no sensing or anomaly detection. Private labels are under restricted/.\n"
    )
    return refresh_checksums(output)


def source_digest():
    source = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*.py")):
        digest.update(str(path.relative_to(source)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def verify_run(directory: Path):
    manifest = SimulationManifest.model_validate_json((directory / "manifest.json").read_text())
    for artifact in manifest.artifacts:
        path = (directory / artifact.uri).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Artifact reference escapes run directory")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError(f"Artifact checksum mismatch: {artifact.uri}")
    return manifest


def load_run(directory: Path):
    verify_run(directory)
    config = PlantConfig.model_validate_json((directory / "plant_config.json").read_text())
    scenario = ScenarioDefinition.model_validate_json(
        (directory / "restricted/scenario.json").read_text()
    )
    faults = [
        FaultInjection.model_validate(f)
        for f in json.loads((directory / "restricted/faults.json").read_text())
    ]
    return PlantSimulator(create_baseline_plant(config, scenario.random_seed), scenario, faults)
