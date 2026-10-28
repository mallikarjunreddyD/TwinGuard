"""Planning correctness, evidence isolation, actual ray geometry and durable API behavior."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from twinguard.inspection.contracts import (
    PlanningSnapshot,
    AssetPlanningState,
    InspectionPlanningRequest,
    SurfaceCoverageEstimate,
    Box,
)
from twinguard.inspection.observations import load_config, fingerprint, snapshot
from twinguard.inspection.coverage import ReferenceSurface, qualified_history
from twinguard.inspection.visibility import look_at, directions
from twinguard.inspection.feasibility import segment_box, route, evaluate
from twinguard.inspection.candidates import generate
from twinguard.inspection.priority import priorities
from twinguard.inspection.optimizer import plan, exact_coverage
from twinguard.inspection.replanning import recommend
from twinguard.core.boundaries import audit_consumers
from twinguard.edge.storage import metadata, put, get, jobs, claim

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def setup():
    c = load_config(ROOT / "configs/inspection/planner.yaml")
    surface = ReferenceSurface(ROOT / c.reference_path, c.reference_sha256, c.cell_m)
    state = PlanningSnapshot(
        snapshot_id="test",
        at=NOW,
        reference_hash=surface.hash,
        assets=[AssetPlanningState(asset_id="BW-01")],
    )
    candidates = generate(surface, state, c, ROOT)
    return c, surface, state, candidates


def test_reference_hash_rejects(setup):
    c, _, _, _ = setup
    with pytest.raises(ValueError, match="hash"):
        ReferenceSurface(ROOT / c.reference_path, "0" * 64)


def test_planner_has_no_privileged_imports():
    assert not audit_consumers(ROOT / "src/twinguard")


@pytest.mark.parametrize("point", [(0, 0, 0), (1, 2, 3), (-2, 4, 2)])
def test_pose_and_sensor_forward(point):
    target = np.asarray(point) + [1, 2, 0.5]
    t = look_at(np.asarray(point, float), target, "lidar-01")
    m = np.array(t.matrix)
    assert np.allclose(m[:3, :3].T @ m[:3, :3], np.eye(3))
    assert np.linalg.det(m[:3, :3]) == pytest.approx(1)
    assert np.allclose(m[:3, 0], (target - point) / np.linalg.norm(target - point))
    assert np.allclose(t.inverse().compose(t).matrix, np.eye(4))


def test_actual_angular_sampling_matches_existing_sensor():
    from twinguard.sensing.acquisition import load_installation
    from twinguard.sensing.lidar import scanning_directions
    from twinguard.sensing.thermal import camera_directions

    installation = load_installation(ROOT / "configs/sensing/L1.yaml")
    lidar = installation.lidar.model_copy(deep=True)
    lidar.noise.angular_sigma_rad = 0
    nominal, _ = scanning_directions(lidar, np.random.default_rng(0))
    assert np.allclose(directions(lidar.model_dump(mode="json"), "lidar"), nominal)
    assert nominal.shape == (16 * 720, 3)
    assert np.allclose(
        directions(installation.thermal.model_dump(mode="json"), "thermal"),
        camera_directions(installation.thermal)[0],
    )


def test_known_area_first_hit_occlusion_and_incidence(tmp_path):
    scene = trimesh.Scene()
    for i, x in enumerate([0, 1]):
        mesh = trimesh.Trimesh(
            vertices=[[x, -0.5, -0.5], [x, 0.5, -0.5], [x, 0.5, 0.5], [x, -0.5, 0.5]],
            faces=[[0, 1, 2], [0, 2, 3]],
            process=False,
        )
        scene.add_geometry(mesh, node_name=f"wall-{i}", geom_name=f"wall-{i}")
    p = tmp_path / "accepted.glb"
    p.write_bytes(scene.export(file_type="glb"))
    s = ReferenceSurface(p, hashlib.sha256(p.read_bytes()).hexdigest())
    assert s.area.sum() == pytest.approx(2)
    r, cos, cells = s.cast(np.array([-1, 0, 0]), np.array([[1, 0, 0], [1, 2, 0]]))
    assert r[0] == pytest.approx(1)
    assert cos[0] == pytest.approx(1)
    assert s.assets[cells[0]] == "wall-0"
    assert np.isinf(r[1])
    assert s.area_of([cells[0], cells[0]]) == pytest.approx(s.area[cells[0]])


@pytest.mark.parametrize(
    "field,value",
    [
        ("budget_s", 0),
        ("budget_views", 0),
        ("budget_views", 13),
        ("maximum_travel_m", float("nan")),
    ],
)
def test_request_validation(field, value):
    with pytest.raises(ValueError):
        InspectionPlanningRequest.model_validate({"request_id": "bad", field: value})


def test_future_observations_and_private_fields_rejected(setup):
    _, s, _, _ = setup
    cov = SurfaceCoverageEstimate(
        asset_id="BW-01",
        reference_hash=s.hash,
        modeled_area_m2=1,
        acquired_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ValueError):
        PlanningSnapshot(
            snapshot_id="bad",
            at=NOW,
            reference_hash=s.hash,
            assets=[AssetPlanningState(asset_id="BW-01")],
            coverage=[cov],
        )
    with pytest.raises(ValueError):
        PlanningSnapshot.model_validate(
            {
                "snapshot_id": "bad",
                "at": NOW,
                "reference_hash": s.hash,
                "assets": [{"asset_id": "BW-01"}],
                "true_pose": np.eye(4).tolist(),
            }
        )


def test_qualified_requires_actual_observed():
    with pytest.raises(ValueError):
        SurfaceCoverageEstimate(
            asset_id="BW-01", reference_hash="a", modeled_area_m2=2, qualified_cells=[1]
        )


def test_observed_is_not_qualified_without_registration(setup):
    _, s, _, _ = setup
    points = s.centers[s.assets == "BW-01"][:20]
    result = s.observed(
        "BW-01",
        points,
        NOW,
        NOW,
        "scan",
        registration_valid=False,
        calibration_supported=True,
        uncertainty_m=0.01,
        qualified_bounds=[[[-5, -5, -5], [5, 5, 5]]],
    )
    assert result.observed_area_m2 > 0 and result.qualified_area_m2 == 0


@pytest.mark.parametrize("age,expected", [(0, True), (3601, False)])
def test_freshness(setup, age, expected):
    c, s, state, _ = setup
    ids = np.where(s.assets == "BW-01")[0][:3].tolist()
    cov = SurfaceCoverageEstimate(
        asset_id="BW-01",
        reference_hash=s.hash,
        modeled_area_m2=10,
        observed_cells=ids,
        qualified_cells=ids,
        acquired_at=NOW - timedelta(seconds=age),
        source_ids=["public"],
    )
    snap = state.model_copy(update={"coverage": [cov]})
    assert bool(qualified_history(s, snap, c)) is expected


def test_deterministic_candidates(setup):
    c, s, state, views = setup
    assert fingerprint(views[0]) == fingerprint(generate(s, state, c, ROOT)[0])
    assert len({v.viewpoint_id for v in views}) == len(views)
    assert all(v.planned_pose.target.reference_id == "plant-01" for v in views)


@pytest.mark.parametrize(
    "constraint,reason",
    [
        ("l2", "unsupported_sensor_precision_L2"),
        ("range", "outside_calibrated_range"),
        ("registration", "insufficient_registration_support"),
        ("no_go", "no_go_volume"),
    ],
)
def test_unsupported_candidates(setup, constraint, reason):
    c, s, state, _ = setup
    c = c.model_copy(deep=True)
    if constraint == "l2":
        c.sensor_path = "configs/sensing/L2.yaml"
    if constraint == "range":
        c.calibrated_range_m = (6, 7)
    if constraint == "registration":
        c.minimum_registration_returns = 100000
    if constraint == "no_go":
        c.no_go = [c.allowed_volume]
    views = generate(s, state, c, ROOT)
    lidar = [v for v in views if v.modality == "lidar"]
    assert all(
        v.feasibility.status == "infeasible" and reason in v.feasibility.reasons for v in lidar
    )
    assert (
        plan(s, state, c, InspectionPlanningRequest(request_id="bad"), views).status
        == "no_viable_viewpoint"
    )


def test_unknown_environment_requires_route_review(setup):
    c, s, state, _ = setup
    c = c.model_copy(update={"map_complete": False})
    views = generate(s, state, c, ROOT)
    assert any(v.feasibility.status == "requires_route_review" for v in views)
    assert (
        plan(s, state, c, InspectionPlanningRequest(request_id="unknown"), views).status
        == "requires_route_review"
    )


def test_static_obstacle_route_and_standoff(setup):
    c, s, _, _ = setup
    assert not route(s, [-3, 0, 1.5], [3, 0, 1.5], c)
    assert "static_standoff_violation" in evaluate(s, [0, 0, 1.5], "BW-01", c, []).reasons


@pytest.mark.parametrize(
    "a,b,hit",
    [([-1, 0, 0], [1, 0, 0], True), ([-1, 2, 0], [1, 2, 0], False), ([0, 0, 0], [0, 0, 0], True)],
)
def test_segment_box(a, b, hit):
    box = Box(lower=(-0.2, -0.2, -0.2), upper=(0.2, 0.2, 0.2))
    assert segment_box(a, b, box) == hit


@pytest.mark.parametrize("method", ["P0", "P1", "P2", "P3"])
def test_budget_union_determinism(setup, method):
    c, s, state, views = setup
    r = InspectionPlanningRequest(request_id=method, method=method, budget_views=2, budget_s=35)
    a = plan(s, state, c, r, views)
    b = plan(s, state, c, r, views)
    assert a.plan_id == b.plan_id and a.steps == b.steps
    assert len(a.steps) <= 2 and a.estimated_duration_s <= 35
    assert len({v.viewpoint_id for v in a.steps}) == len(a.steps)
    union = {i for step in a.steps for i in step.utility.new_cells}
    assert a.expected_new_usable_area_m2 == pytest.approx(s.area_of(union))
    assert sum(step.marginal_area_m2 for step in a.steps) == pytest.approx(
        a.expected_new_usable_area_m2
    )
    assert a.approval_status == "pending_operator_review"


def test_empty_budget_and_pool(setup):
    c, s, state, views = setup
    assert not plan(
        s, state, c, InspectionPlanningRequest(request_id="tiny", budget_s=0.001), views
    ).steps
    assert (
        plan(s, state, c, InspectionPlanningRequest(request_id="empty"), []).status
        == "no_viable_viewpoint"
    )


def test_repeat_avoidance(setup):
    c, s, state, views = setup
    state = state.model_copy(update={"attempted_viewpoints": [v.viewpoint_id for v in views]})
    assert not plan(s, state, c, InspectionPlanningRequest(request_id="repeat"), views).steps


def test_exact_reference_and_limit(setup):
    c, s, state, views = setup
    small = [v for v in views if v.feasibility.status == "feasible"][:4]
    r = InspectionPlanningRequest(request_id="exact", method="P1", budget_views=1)
    greedy = plan(s, state, c, r, small)
    exact = exact_coverage(s, small, c, r)
    assert exact["area_m2"] == pytest.approx(greedy.expected_new_usable_area_m2)
    with pytest.raises(ValueError):
        exact_coverage(s, small * 3, c, r)


def test_critical_access_and_thermal_no_spatial_claim(setup):
    c, s, state, views = setup
    states = snapshot(
        NOW,
        ["BW-01"],
        {},
        [
            {
                "event_id": "red",
                "asset_id": "BW-01",
                "severity": "red",
                "lifecycle": "active",
                "hazard_id": "critical_pressure_limit",
            }
        ],
    )
    snap = state.model_copy(update={"assets": states})
    assert priorities(s, snap, c)[0].access == "review_required"
    p = plan(s, snap, c, InspectionPlanningRequest(request_id="red"), views)
    assert p.relevant_advisories == ["red"]
    assert "Explicit operator approval" in p.explanation.recommended_actions[0]
    assert snap.assets[0].severity == "red"
    c = c.model_copy(update={"restricted_assets": ["BW-01"]})
    assert not plan(
        s, snap, c, InspectionPlanningRequest(request_id="restricted"), generate(s, snap, c, ROOT)
    ).steps


def test_no_missing_to_healthy_and_missing_criticality(setup):
    c, s, state, _ = setup
    c = c.model_copy(update={"criticality": {}})
    priority = priorities(s, state, c)[0]
    assert priority.terms["criticality"] == 0.5 and priority.terms["deficiency"] == 1
    assert state.assets[0].severity == "unknown"
    assert any("Criticality missing" in r for r in priority.reasons)


def test_replanning_lineage(setup):
    c, s, state, views = setup
    p = plan(s, state, c, InspectionPlanningRequest(request_id="initial"), views)
    with pytest.raises(ValueError):
        recommend(p, state)
    assert (
        recommend(p, state.model_copy(update={"previous_plan_id": p.plan_id})).outcome == "replan"
    )


@pytest.fixture
def database(tmp_path, monkeypatch):
    db = create_engine(
        "sqlite:///" + str(tmp_path / "edge.db"), connect_args={"check_same_thread": False}
    )
    metadata.create_all(db)
    monkeypatch.setenv("TWINGUARD_ARTIFACTS", str(tmp_path / "artifacts"))
    with db.begin() as c:
        put(c, "asset", "BW-01", {"asset_id": "BW-01"})
    return db


def test_durable_plan_idempotent_retry_and_api(database, monkeypatch):
    from twinguard.edge import planning, api
    from twinguard.api.app import app

    monkeypatch.setattr(api, "db", lambda: database)
    from twinguard.edge import planning_api

    monkeypatch.setattr(planning_api, "db", lambda: database)
    request = InspectionPlanningRequest(request_id="durable", budget_views=1)
    a = planning.submit(database, request, "operator")
    assert a == planning.submit(database, request, "operator")
    with pytest.raises(ValueError):
        planning.submit(database, request.model_copy(update={"budget_views": 2}), "operator")
    # Expired planning lease is recovered without touching IoT kind.
    old = claim(database, "planning", "crashed", lease_s=0)
    assert old
    assert planning.run_one(database, "recovered")
    with database.connect() as c:
        row = get(c, "planning_request", "durable")
        p = planning.get_plan(c, row["plan_id"])
        assert p["steps"] and c.execute(select(jobs.c.attempts)).scalar_one() == 2
    client = TestClient(app)
    assert client.get("/api/v1/inspection-plans").status_code == 401
    app.dependency_overrides[api.user] = lambda: {"actor": "viewer", "role": "viewer"}
    try:
        assert (
            client.post(
                "/api/v1/inspection-plans", json=request.model_dump(mode="json")
            ).status_code
            == 403
        )
        assert client.get("/api/v1/inspection-plans/" + p["plan_id"]).status_code == 200
        assert client.get("/api/v1/inspection-plans/" + p["plan_id"] + "/coverage").json()[
            "centers_world_m"
        ]
        assert (
            client.post(
                "/api/v1/inspection-plans/" + p["plan_id"] + "/review",
                json={"decision": "approved_for_simulation", "rationale": "reviewed"},
            ).status_code
            == 403
        )
        assert not any(
            "execute" in r.path or "flight" in r.path for r in app.routes if hasattr(r, "path")
        )
    finally:
        app.dependency_overrides.clear()
