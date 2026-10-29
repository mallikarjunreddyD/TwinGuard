"""Controller-only demonstration from a reviewed backend plan to real virtual sensing."""

from pathlib import Path
import json
import time
import io
import zipfile
import uuid
import httpx
from twinguard.inspection.observations import fingerprint
from twinguard.core.spatial import Transform
from twinguard.core.contracts import InspectionSchedule, InspectionCapture
from twinguard.core.observations import load_public_observations
from twinguard.edge.contracts import Envelope, now
from twinguard.edge.protocols import publish
from twinguard.evaluation.experiments import setup_scenario
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.sensing.acquisition import acquire, load_installation
from twinguard.analytics.pipeline import save_json

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/mnt/d/TwinGuard/phase7-V7-reviewed-reinspection")
URL = "http://localhost:19080/api/v1"


def main():
    OUT.mkdir(exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    headers = {"Authorization": "Bearer " + secrets["operator"]}
    client = httpx.Client(timeout=60)
    initial_request = "phase7-initial-" + uuid.uuid4().hex
    response = client.post(
        URL + "/inspection-plans",
        headers=headers,
        json={"request_id": initial_request, "method": "P0", "budget_views": 1, "budget_s": 70},
    )
    response.raise_for_status()
    for _ in range(120):
        status = client.get(
            URL + "/inspection-plans/requests/" + initial_request, headers=headers
        ).json()
        if status["status"] == "completed":
            break
        if status["status"] == "failed":
            raise RuntimeError(status["error"])
        time.sleep(0.5)
    initial_plan = client.get(
        URL + "/inspection-plans/" + status["plan_id"], headers=headers
    ).json()
    history = [initial_plan]
    plan = next(
        client.get(URL + "/inspection-plans/" + r["plan_id"], headers=headers).json()
        for r in history
        if r["status"] == "recommended"
    )
    selected = next(
        v for v in plan["candidates"] if v["viewpoint_id"] == plan["steps"][0]["viewpoint_id"]
    )
    if selected["modality"] != "lidar":
        raise ValueError("Demonstration requires a selected supported LiDAR view")
    save_json(OUT / "frozen-plan.json", plan)
    save_json(
        OUT / "plan-ready.json",
        {
            "plan_sha256": fingerprint(plan),
            "at": now().isoformat(),
            "scope": "Software simulation test only",
        },
    )
    response = client.post(
        URL + "/inspection-plans/" + plan["plan_id"] + "/review",
        headers=headers,
        json={
            "decision": "approved_for_simulation",
            "rationale": "Authorized Phase 7 software validation; no physical flight approval",
            "acknowledges_critical_process": True,
        },
    )
    response.raise_for_status()
    scenario, faults = setup_scenario(
        ROOT, "phase7-platform-demo", 19000, kind="geometric", amplitude=0.02
    )
    install = load_installation(ROOT / "configs/sensing/L1.yaml")
    install.event_poses = {"lidar-01-t_60": Transform.model_validate(selected["planned_pose"])}
    scenario.inspections = [
        InspectionSchedule(sensor_id="lidar-01", offset_s=t, modality="lidar") for t in (0, 60)
    ]
    scenario.sensor_config_ids = ["lidar-01"]
    simulator = PlantSimulator(
        create_baseline_plant(load_plant_config(ROOT / "configs/plant.yaml"), 19000),
        scenario,
        faults,
    )
    acquire(simulator.sensing_reader(), scenario, install, OUT / "measurements", modality="all")
    captures = [
        r
        for r in load_public_observations(OUT / "measurements")
        if isinstance(r, InspectionCapture)
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((OUT / "measurements").rglob("*")):
            if path.is_file() and (
                "observations" in path.relative_to(OUT / "measurements").parts
                or path.name == "manifest.json"
            ):
                archive.write(path, str(path.relative_to(OUT / "measurements")))
    response = client.post(
        URL + "/inspection-imports",
        headers={"Authorization": headers["Authorization"], "Content-Type": "application/zip"},
        content=buffer.getvalue(),
    )
    response.raise_for_status()
    digest = response.json()["sha256"]
    job_id = "simulation-" + uuid.uuid4().hex
    at = now()
    env = Envelope(
        message_id=job_id,
        source_id="demo-uav",
        kind="inspection",
        sequence=0,
        sequence_epoch=job_id,
        emitted_at=at,
        provenance_id=captures[-1].provenance_id,
        mode="simulation_replay",
        replay_acquired_at=at,
        replay_source_anchor_at=max(r.acquired_at for r in captures),
        artifact_sha256=digest,
    )
    save_json(OUT / "delivery-envelope.json", env)
    publish([env], secrets["demo-uav"], host="localhost", port=19083)
    result = None
    for _ in range(180):
        response = client.get(URL + "/inspections/" + job_id, headers=headers)
        if response.status_code == 200:
            result = response.json()
            break
        time.sleep(0.5)
    if result is None:
        raise RuntimeError("No completed inspection")
    binding = {
        "result_id": job_id,
        "viewpoint_id": selected["viewpoint_id"],
        "inspection_job_id": job_id,
        "requested_pose_sha256": fingerprint(selected["planned_pose"]),
    }
    response = client.post(
        URL + "/inspection-plans/" + plan["plan_id"] + "/simulation-results",
        headers=headers,
        json=binding,
    )
    response.raise_for_status()
    save_json(OUT / "linked-result.json", response.json())
    request_id = "after-" + job_id
    response = client.post(
        URL + "/inspection-plans",
        headers=headers,
        json={
            "request_id": request_id,
            "previous_plan_id": plan["plan_id"],
            "method": "P3v2",
            "budget_views": 2,
            "budget_s": 70,
        },
    )
    response.raise_for_status()
    for _ in range(120):
        state = client.get(URL + "/inspection-plans/requests/" + request_id, headers=headers).json()
        if state["status"] == "completed":
            break
        if state["status"] == "failed":
            raise RuntimeError(state["error"])
        time.sleep(0.5)
    nextplan = client.get(URL + "/inspection-plans/" + state["plan_id"], headers=headers).json()
    save_json(OUT / "replanned.json", nextplan)
    condition = client.get(URL + "/assets/BW-01/condition", headers=headers).json()
    save_json(OUT / "F1-condition.json", condition)
    save_json(
        OUT / "report.json",
        {
            "plan_id": plan["plan_id"],
            "viewpoint_id": selected["viewpoint_id"],
            "inspection_job_id": job_id,
            "replan_id": nextplan["plan_id"],
            "status": result["geometric"][0]["status"],
            "regions": len(result["geometric"][0]["regions"]),
            "coverage_records": len(result.get("surface_coverage", [])),
            "F1_severity": condition["assessment"]["severity"],
            "operator_scope": "Local software-test principal only; no human/physical commissioning evidence",
        },
    )
    print((OUT / "report.json").read_text(), flush=True)


if __name__ == "__main__":
    main()
