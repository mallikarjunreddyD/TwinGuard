"""Controller-only rejected-view probes: test L2 physics without calling the pose viable."""

from pathlib import Path
import json
from datetime import timedelta
import numpy as np
from twinguard.evaluation.experiments import setup_scenario
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.sensing.acquisition import acquire, load_installation
from twinguard.core.spatial import Transform
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations
from twinguard.analytics.pipeline import analyze_geometry, save_json, seal_predictions
from twinguard.analytics.reference import load_reference
from twinguard.analytics.config import AnalyticsConfig
from twinguard.fusion.models import FusionState, ProcessingRecord
from twinguard.fusion.policies import load_policy
from twinguard.fusion.engine import assess
from twinguard.fusion import adapters

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/outputs/phase6-L2-probes"


def main():
    OUT.mkdir(exist_ok=False)
    rows = []
    for trial in sorted(
        (ROOT / "experiments/outputs/phase6-E5-recovered/shard-0").glob("E5-S05-*")
    ):
        seed = int(trial.name.rsplit("-", 1)[1])
        plan = json.loads((trial / "P3/plan.json").read_text())
        candidate = min(
            [
                v
                for v in plan["candidates"]
                if v["asset_id"] == "BW-01" and v["modality"] == "lidar"
            ],
            key=lambda v: (
                abs(v["planned_pose"]["matrix"][0][3]),
                abs(v["expected_range_m"] - 3.4),
                v["viewpoint_id"],
            ),
        )
        work = OUT / trial.name
        save_json(work / "frozen-rejected-candidate.json", candidate)
        save_json(
            work / "controller-scope.json",
            {
                "scope": "Authorized software-only diagnostic of a rejected pose, not an operational plan or flight authorization",
                "reason": "Measure whether a different view repairs L2 noise; planner still declares no viable viewpoint",
            },
        )
        scenario, faults = setup_scenario(
            ROOT, trial.name, seed, kind="geometric", amplitude=[0.01, 0.02, 0.03, 0.05][seed % 4]
        )
        rng = np.random.default_rng(seed)
        faults[0].center_local_m = (
            float(rng.uniform(-0.25, 0.25)),
            0,
            float(rng.uniform(0.9, 1.5)),
        )
        install = load_installation(ROOT / "configs/sensing/L2.yaml")
        install.lidar.pose = Transform.model_validate(candidate["planned_pose"])
        install.event_poses = {}
        scenario.sensor_config_ids = ["lidar-01"]
        simulator = PlantSimulator(
            create_baseline_plant(load_plant_config(ROOT / "configs/plant.yaml"), seed),
            scenario,
            faults,
        )
        acquire(
            simulator.sensing_reader(),
            scenario,
            install,
            work / "measurements",
            modality="lidar",
            time_s=72,
        )
        initial = sorted(
            [
                v
                for v in load_public_observations(trial / "initial")
                if isinstance(v, InspectionCapture) and v.modality == "lidar"
            ],
            key=lambda c: c.acquired_at,
        )[0]
        current = next(
            v
            for v in load_public_observations(work / "measurements")
            if isinstance(v, InspectionCapture)
        )
        reg, geom = analyze_geometry(
            trial / "initial" / initial.artifact.uri,
            work / "measurements" / current.artifact.uri,
            AnalyticsConfig(),
            load_reference(ROOT / "configs/analytics/accepted_reference.json"),
            work / "analysis",
            methods=["B3.1"],
            improved_calibration=json.loads(
                (ROOT / "configs/fusion/calibration/geometry_b31.json").read_text()
            ),
        )["B3.1"]
        at = current.acquired_at + timedelta(seconds=1)
        proc = ProcessingRecord(
            source_id=geom.analysis_id,
            received_at=at,
            processed_at=at,
            available_at=at,
            basis="simulated_replay",
            rationale="Rejected-candidate simulation probe; no physical acquisition",
            clock_quality="synchronized",
        )
        evidence = adapters.geometry(geom, reg, proc, current.provenance_id)
        state = FusionState.model_validate_json((trial / "P0/F1.json").read_text())
        state, trace = assess(
            state, evidence, load_policy(ROOT / "configs/fusion/hazards.yaml"), at
        )
        save_json(work / "F1.json", state)
        seal_predictions(
            work,
            {"rejected_viewpoint_id": candidate["viewpoint_id"]},
            [str(trial / "initial/manifest.json")],
        )
        rows.append(
            {
                "seed": seed,
                "viewpoint_id": candidate["viewpoint_id"],
                "planner_feasibility": candidate["feasibility"]["status"],
                "geometry_status": geom.status,
                "registration_status": reg.status,
                "qualified_patches": sum(
                    p.status == "valid" and p.calibration_support >= 10 for p in geom.patches
                ),
                "valid_returns": current.quality_indicators["valid_returns"],
                "geometric_positive_evidence": sum(e.finding == "positive" for e in evidence),
            }
        )
    save_json(
        OUT / "report.json",
        {
            "scope": "Thirty actual L2 scans from frozen rejected alternate poses; never presented as selected feasible inspections",
            "rows": rows,
        },
    )
    save_json(ROOT / "docs/phase6/L2_probes.json", json.loads((OUT / "report.json").read_text()))
    print(
        "L2 probes", len(rows), "qualified", sum(r["qualified_patches"] for r in rows), flush=True
    )


if __name__ == "__main__":
    main()
