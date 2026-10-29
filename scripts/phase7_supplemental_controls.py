"""Separately frozen controls: genuinely missed initial view, independent occluder,
and predeclared tiny scoped healthy coverage. Production candidates remain frozen.
The acquisition wrapper changes only nominal public initial-view direction or adds
an independent known static obstacle to both sensing and the accepted public map.
"""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import argparse
import hashlib
import json
import time
import numpy as np
import trimesh
import twinguard.evaluation.phase7_planners as controller
from twinguard.evaluation.campaigns import Campaign, atomic_json, digest
from twinguard.inspection.visibility import look_at
from twinguard.inspection.contracts import Box
from twinguard.sensing.read import Surface

ROOT = Path(__file__).resolve().parents[1]
MODES = ("missed_left", "independent_occluder", "sufficient_scope")


def one(task):
    output, mode, seed = task
    output = Path(output)
    original_acquire = controller.acquire
    original_config = controller.load_config
    original_simulator = controller.PlantSimulator
    original_snapshot = controller.PlanningSnapshot
    roi = []

    def config(path):
        cfg = original_config(path)
        if mode == "independent_occluder":
            cfg.reference_path = str(output / "accepted-independent-occluder.glb")
            cfg.reference_sha256 = hashlib.sha256(Path(cfg.reference_path).read_bytes()).hexdigest()
            cfg.no_go.append(Box(lower=(0.175, 1.09, 1.05), upper=(0.625, 1.21, 2.15)))
        if mode == "sufficient_scope":
            surface = controller.ReferenceSurface(
                ROOT / cfg.reference_path, cfg.reference_sha256, cfg.cell_m
            )
            ids = np.flatnonzero((surface.assets == "BW-01") & (abs(surface.centers[:, 1]) < 1e-6))
            if not len(ids):
                raise ValueError("No declared front-wall ROI available")
            roi.extend(
                [int(ids[np.argmin(np.linalg.norm(surface.centers[ids] - [0, 0, 1.55], axis=1))])]
            )
        return cfg

    def acquisition(reader, scenario, installation, path, **kwargs):
        if mode == "missed_left" and kwargs.get("time_s") == 60:
            installation = installation.model_copy(deep=True)
            installation.lidar.pose = look_at(
                np.array([-0.9, 2.4, 1.55]), np.array([-1.15, -0.065, 1.55]), "lidar-01"
            )
            installation.lidar.horizontal_fov_rad = 0.30
        return original_acquire(reader, scenario, installation, path, **kwargs)

    class Simulator:
        def __init__(self, *args, **kwargs):
            self.original = original_simulator(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.original, name)

        def sensing_reader(self):
            reader = self.original.sensing_reader()
            if mode != "independent_occluder":
                return reader
            mesh = trimesh.creation.box(extents=[0.45, 0.12, 1.1])
            mesh.apply_translation([0.4, 1.15, 1.6])

            class Reader:
                def read_process_at(self, t):
                    return reader.read_process_at(t)

                def read_at(self, t):
                    view = reader.read_at(t)
                    obstacle = Surface(
                        "ENV-STATIC-01",
                        mesh.vertices,
                        mesh.faces,
                        np.full(len(mesh.vertices), view.ambient_temperature_c),
                    )
                    return replace(view, surfaces=view.surfaces + (obstacle,))

            return Reader()

    def snapshot(**kwargs):
        value = original_snapshot(**kwargs)
        if mode == "sufficient_scope":
            value.required_region_cells = {"BW-01": list(roi)}
        return value

    controller.load_config = config
    controller.acquire = acquisition
    controller.PlantSimulator = Simulator
    controller.PlanningSnapshot = snapshot
    family = "healthy_wide" if mode == "sufficient_scope" else "previously_unconfirmed"
    try:
        result = controller.trial((str(ROOT), str(output / mode), family, seed, None))
        for row in result:
            trials = output / mode / "trials"
            possible = [trials / f"{family}-{seed}", *trials.glob(f"{family}-{seed}-attempt-*")]
            chosen = None
            for candidate in possible:
                plan_path = candidate / row["detector"] / row["method"] / "plan.json"
                if (
                    plan_path.is_file()
                    and controller.fingerprint(json.loads(plan_path.read_text()))
                    == row["plan_hash"]
                ):
                    chosen = candidate
                    break
            if chosen is None:
                raise ValueError("Cannot bind completed result to preserved frozen plan")
            snap = json.loads((chosen / row["detector"] / "initial-snapshot.json").read_text())
            coverage = {i for c in snap["coverage"] for i in c["qualified_cells"]}
            row["supplemental_control"] = mode
            row["scoped_roi_cells"] = list(roi)
            row["scope_actually_qualified"] = bool(roi) and set(roi) <= coverage
            row["case_id"] = f"{mode}-{seed}"
        return result
    finally:
        controller.acquire = original_acquire
        controller.load_config = original_config
        controller.PlantSimulator = original_simulator
        controller.PlanningSnapshot = original_snapshot


def main(output, smoke=False, resume=False, workers=2):
    output = output.resolve()
    if not resume:
        output.mkdir(parents=True, exist_ok=False)
    scene = trimesh.load(ROOT / "configs/edge/plant.glb", force="scene", process=False)
    obstacle = trimesh.creation.box(extents=[0.45, 0.12, 1.1])
    obstacle.apply_translation([0.4, 1.15, 1.6])
    scene.add_geometry(
        obstacle, node_name="ENV-STATIC-01_obstacle", geom_name="ENV-STATIC-01_obstacle"
    )
    map_bytes = (
        (output / "accepted-independent-occluder.glb").read_bytes()
        if resume
        else scene.export(file_type="glb")
    )
    seeds = list(range(17101, 17102) if smoke else range(17000, 17030))
    configuration = {
        "purpose": __doc__,
        "seeds": seeds,
        "modes": MODES,
        "scope": "One predeclared accepted-map cell nearest (0,0,1.55) on the nominal front face, never whole-asset health",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "frozen_candidates": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("analytics", "inspection", "fusion", "sensing")
            for p in sorted((ROOT / "src/twinguard" / folder).glob("*.py"))
        },
        "accepted_occluder_map_sha256": hashlib.sha256(map_bytes).hexdigest(),
        "count": len(seeds) * len(MODES),
        "maximum_new_campaign_bytes": 10 * 1024**3,
    }
    if resume:
        state = json.loads((output / "campaign.json").read_text())
        before = json.loads(json.dumps(state))
        old = dict(state["configuration"])
        new = dict(configuration)
        old_source = old.pop("source_sha256")
        new_source = new.pop("source_sha256")
        if old != json.loads(json.dumps(new)):
            raise ValueError(
                "Scientific candidate/protocol change cannot use infrastructure resume"
            )
        atomic_json(output / f"campaign.before-memory-resume-{time.time_ns()}.json", before)
        state.setdefault("infrastructure_resumes", []).append(
            {
                "reason": "Measured OSError ENOMEM; single worker, four tasks per process; metadata lookup binds frozen plan after preserved interrupted attempts",
                "prior_configuration_hash": state["configuration_hash"],
                "old_controller_sha256": old_source,
                "new_controller_sha256": new_source,
                "workers": workers,
                "tasks_per_explicit_process_shard": 1,
                "scientific_candidates_unchanged": True,
            }
        )
        state["configuration"] = configuration
        state["configuration_hash"] = digest(configuration)
        atomic_json(output / "campaign.json", state)
    campaign = Campaign(output, configuration, resume=resume)
    if not resume:
        (output / "accepted-independent-occluder.glb").write_bytes(map_bytes)
    tasks = [
        (str(output), mode, seed)
        for seed in seeds
        for mode in MODES
        if f"{mode}-{seed}" not in campaign.state["completed"]
    ]
    try:
        for begin in range(0, len(tasks), 1):
            with ProcessPoolExecutor(max_workers=workers) as pool:
                for result in pool.map(one, tasks[begin : begin + 1]):
                    campaign.commit(result[0]["case_id"], result)
        campaign.finish(configuration["count"])
    except Exception as exc:
        campaign.fail(exc)
        raise
    atomic_json(output / "source_configuration.json", configuration)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    a = parser.parse_args()
    main(a.output, a.smoke, a.resume, a.workers)
