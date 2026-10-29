"""Restricted post-seal useful-view and payload accounting; never a planner input."""

from pathlib import Path
import argparse
import hashlib
import json
import io
import numpy as np
from twinguard.inspection.coverage import ReferenceSurface
from twinguard.inspection.observations import load_config
from twinguard.core.analytics_contracts import GeometryResult
from twinguard.evaluation.phase7_research import region_matches
from twinguard.evaluation.campaigns import atomic_json

ROOT = Path(__file__).resolve().parents[1]


def main(output):
    source = ROOT / "experiments/outputs/phase7-V3-heldout-planners"
    state = json.loads((source / "campaign.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    config = load_config(ROOT / "configs/inspection/planner.yaml")
    surface = ReferenceSurface(ROOT / config.reference_path, config.reference_sha256, config.cell_m)
    count = 0
    for ident, checksum in state["completed"].items():
        destination = output / (ident + ".json")
        if destination.exists():
            previous = json.loads(destination.read_text())
            if previous["source_case_sha256"] != checksum:
                raise ValueError("Changed source case")
            continue
        case = source / "cases" / (ident + ".json")
        data = case.read_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError("Source journal integrity failure")
        rows = json.loads(data)
        work = source / "trials" / ident
        public = []
        for row in rows:
            directory = work / row["detector"] / row["method"]
            seal = json.loads((directory / "predictions_ready.json").read_text())
            result_bytes = (directory / "results.json").read_bytes()
            if hashlib.sha256(result_bytes).hexdigest() != seal["artifacts"]["results.json"]:
                raise ValueError("Sealed result mismatch")
            public.append((row, directory, json.loads(result_bytes), seal))
        # Restricted labels are opened only after all public result hashes check.
        truth = json.loads((work / "evaluation_private/truth.json").read_text())
        fault = next((f for f in truth["fault_states"] if f["asset_id"] == "BW-01"), None)
        derived = []
        verified = {}
        for row, directory, results, seal in public:
            snapshot = json.loads((work / row["detector"] / "initial-snapshot.json").read_text())
            plan_data = json.loads((directory / "plan.json").read_text())
            candidate_map = {v["viewpoint_id"]: v for v in plan_data["candidates"]}
            observed_initial = {i for c in snapshot["coverage"] for i in c["observed_cells"]}
            qualified_initial = {i for c in snapshot["coverage"] for i in c["qualified_cells"]}
            observed = set(observed_initial)
            qual_cells = set(qualified_initial)
            predicted_visible = set()
            predicted_usable = set()
            useful = 0
            payload_bytes = 0
            pipeline_s = 0.0
            qualified = 0
            fp = 0
            for index, result in enumerate(results):
                geometry = GeometryResult.model_validate(result["geometry"])
                fp += int(not fault and geometry.status == "valid" and bool(geometry.regions))
                qualified += int(geometry.status == "valid")
                pred = directory / f"analysis-{index}"
                input_seal = json.loads((pred / "predictions_ready.json").read_text())[
                    "public_inputs"
                ]
                for kind in ("baseline", "current"):
                    path = Path(input_seal[kind])
                    expected = input_seal[kind + "_payload_sha256"]
                    key = str(path.resolve())
                    if key not in verified:
                        verified[key] = hashlib.sha256(path.read_bytes()).hexdigest()
                    if verified[key] != expected:
                        raise ValueError("Raw public capture checksum mismatch")
                    if kind == "current":
                        payload_bytes += path.stat().st_size
                registered_path = pred / row["detector"] / "registered_current.npz"
                registered_bytes = registered_path.read_bytes()
                if (
                    hashlib.sha256(registered_bytes).hexdigest()
                    != seal["artifacts"][
                        f"analysis-{index}/{row['detector']}/registered_current.npz"
                    ]
                ):
                    raise ValueError("Registered public payload checksum mismatch")
                with np.load(io.BytesIO(registered_bytes), allow_pickle=False) as arrays:
                    points = arrays["points_m"]
                bounds = []
                for patch in geometry.patches:
                    if (
                        patch.status == "valid"
                        and patch.calibration_support >= 10
                        and patch.asset_id == "BW-01"
                    ):
                        half = float(patch.scale_m or 0.08) / np.sqrt(3)
                        center = np.asarray(patch.center_world_m)
                        bounds.append([(center - half).tolist(), (center + half).tolist()])
                registration = result["registration"]
                coverage = surface.observed(
                    "BW-01",
                    points,
                    geometry.acquired_at,
                    geometry.acquired_at,
                    geometry.current_capture_id,
                    registration["status"] == "valid",
                    geometry.status == "valid"
                    and geometry.measurement_basis == "localized_relative",
                    float(registration["uncertainty_score_m"]),
                    bounds,
                )
                observed.update(coverage.observed_cells)
                qual_cells.update(coverage.qualified_cells)
                candidate = candidate_map[result["viewpoint_id"]]
                predicted_visible.update(
                    i for i in candidate["predicted_visible_cells"] if surface.assets[i] == "BW-01"
                )
                predicted_usable.update(
                    i for i in candidate["predicted_usable_cells"] if surface.assets[i] == "BW-01"
                )
                # Only now apply restricted footprint labels to the verified public result.
                matches = region_matches(geometry, fault)
                useful += int(any(matches))
                pipeline_s += json.loads((pred / "runtime.json").read_text())["runtime_s"]
            if bool(useful) != row["new_localized"] or len(results) != row["views"]:
                raise ValueError("Derived view metrics disagree with frozen case evaluation")
            optimization = json.loads((directory / "plan.json").read_text())[
                "optimization_runtime_s"
            ]
            for path in directory.glob("replan-*.json"):
                optimization += json.loads(path.read_text())["optimization_runtime_s"]
            actual_qualified = surface.area_of(qual_cells - qualified_initial)
            if not np.isclose(actual_qualified, row["new_qualified_area_m2"], rtol=1e-9, atol=1e-9):
                raise ValueError("Recomputed qualified coverage disagrees with frozen case")
            derived.append(
                {
                    "case_id": ident,
                    "seed": row["seed"],
                    "method": row["method"],
                    "detector": row["detector"],
                    "views": len(results),
                    "useful_localized_views": useful,
                    "qualified_views": qualified,
                    "healthy_positive_views": fp,
                    "new_capture_payload_bytes": payload_bytes,
                    "analysis_wall_s": pipeline_s,
                    "optimizer_inner_wall_s": optimization,
                    "mission_proxy_s": row["mission_proxy_s"],
                    "predicted_visible_new_area_m2": surface.area_of(
                        predicted_visible - observed_initial
                    ),
                    "actual_observed_new_area_m2": surface.area_of(observed - observed_initial),
                    "visibility_prediction_error_m2": surface.area_of(observed - observed_initial)
                    - surface.area_of(predicted_visible - observed_initial),
                    "predicted_usable_new_area_m2": surface.area_of(
                        predicted_usable - qualified_initial
                    ),
                    "actual_qualified_new_area_m2": actual_qualified,
                }
            )
        atomic_json(
            destination,
            {
                "source_case_sha256": checksum,
                "rows": derived,
                "verification": "Sealed results verified before labels; raw baseline/current and registered payload SHAs verified before per-view footprint matching; qualification recomputed without true hit labels",
                "limitation": "Inner optimizer timing excludes P3v2 suitability preprocessing; controller CPU/wall values include acquisition-cache overhead",
            },
        )
        count += 1
    print(
        "New derived cases",
        count,
        "journal cases",
        len(state["completed"]),
        "status",
        state["status"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    main(args.output)
