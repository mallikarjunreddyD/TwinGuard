"""Calibration applicability, public-only planning, compatibility and recoverable experiments."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
import copy
import json
import numpy as np
import pytest
from pydantic import ValidationError
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.pipeline import analyze_geometry
from twinguard.analytics.reference import load_reference
from twinguard.analytics.view_calibration import (
    applicability,
    planned_applicability,
    acquisition_signature,
    pose_distance,
)
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations
from twinguard.core.boundaries import audit_consumers
from twinguard.inspection.contracts import (
    BaselineInspectionSupport,
    PlanningSnapshot,
    AssetPlanningState,
    InspectionPlanningRequest,
)
from twinguard.inspection.coverage import ReferenceSurface
from twinguard.inspection.observations import load_config
from twinguard.inspection.candidates import generate
from twinguard.inspection.qualified_optimizer import select_plan
from twinguard.evaluation.campaigns import Campaign, resource_preflight

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def model():
    return json.loads((ROOT / "configs/validation/view_calibration.json").read_text())


@pytest.fixture(scope="module")
def public_capture():
    path = ROOT / "configs/fusion/history/observations/lidar/trial-0000-lidar-01-t_0.json"
    capture = InspectionCapture.model_validate_json(path.read_text())
    bundle = json.loads((ROOT / "configs/validation/view_calibration.json").read_text())
    domain = next(d for d in bundle["domains"] if d["domain_id"] == "reference")
    return capture.model_copy(update={"acquisition_parameters": domain["sensor_signature"]})


def test_view_pose_geometry_is_not_a_probability():
    m = np.eye(4)
    n = m.copy()
    n[0, 3] = 2
    assert pose_distance(m, n) == pytest.approx((2, 0))


def test_applicability_uses_reported_poses_and_independent_support(model, public_capture):
    domain = next(d for d in model["domains"] if d["domain_id"] == "reference")
    capture = public_capture.model_copy(deep=True)
    capture.sensor_pose = capture.sensor_pose.model_copy(update={"matrix": domain["baseline_pose"]})
    result, selected = applicability(capture, capture, model)
    assert (
        result["applicable"]
        and selected["independent_fit_scans"] >= 10
        and selected["independent_screen_scans"] >= 10
    )


@pytest.mark.parametrize(
    "problem",
    [
        "far_pose",
        "wrong_sensor",
        "wrong_frame",
        "L2",
        "not_enough_fit",
        "not_enough_screen",
        "no_domain",
    ],
)
def test_unqualified_domains_abstain(model, public_capture, problem):
    bundle = copy.deepcopy(model)
    domain = next(d for d in bundle["domains"] if d["domain_id"] == "reference")
    b = public_capture.model_copy(deep=True)
    b.sensor_pose = b.sensor_pose.model_copy(update={"matrix": domain["baseline_pose"]})
    c = b.model_copy(deep=True)
    if problem == "far_pose":
        matrix = np.array(c.sensor_pose.matrix)
        matrix[0, 3] += 3
        c.sensor_pose = c.sensor_pose.model_copy(update={"matrix": matrix.tolist()})
    if problem == "wrong_sensor":
        c = c.model_copy(update={"sensor_id": "unrecognized"})
    if problem == "wrong_frame":
        c = c.model_copy(
            update={
                "sensor_pose": c.sensor_pose.model_copy(
                    update={
                        "target": c.sensor_pose.target.model_copy(
                            update={"reference_id": "other-site"}
                        )
                    }
                )
            }
        )
    if problem == "L2":
        c.acquisition_parameters["range_sigma_m"] = 0.03
    if problem == "not_enough_fit":
        for d in bundle["domains"]:
            d["independent_fit_scans"] = 9
    if problem == "not_enough_screen":
        for d in bundle["domains"]:
            d["independent_screen_scans"] = 9
    if problem == "no_domain":
        bundle["domains"] = []
    result, selected = applicability(b, c, bundle)
    assert not result["applicable"] and selected is None and result["reasons"]


def test_planned_pose_is_independently_rechecked_on_acquisition(model, public_capture):
    domain = next(d for d in model["domains"] if d["domain_id"] == "reference")
    b = public_capture.model_copy(deep=True)
    b.sensor_pose = b.sensor_pose.model_copy(update={"matrix": domain["baseline_pose"]})
    decision, _ = planned_applicability(
        b.sensor_pose, b.sensor_pose, acquisition_signature(b), model
    )
    assert decision["applicable"]
    actual = b.model_copy(deep=True)
    matrix = np.array(actual.sensor_pose.matrix)
    matrix[1, 3] += 2
    actual.sensor_pose = actual.sensor_pose.model_copy(update={"matrix": matrix.tolist()})
    assert not applicability(b, actual, model)[0]["applicable"]


def test_causal_baseline_rejects_private_and_future_fields(public_capture):
    args = dict(
        capture_id="public",
        reference_hash="reference",
        reported_pose=public_capture.sensor_pose,
        acquired_at=public_capture.acquired_at,
        available_at=public_capture.received_at,
        acquisition_parameters=public_capture.acquisition_parameters,
    )
    with pytest.raises(ValidationError):
        BaselineInspectionSupport(**args, true_pose=public_capture.sensor_pose)
    support = BaselineInspectionSupport(**args)
    with pytest.raises(ValidationError):
        PlanningSnapshot(
            snapshot_id="future",
            at=support.acquired_at - timedelta(seconds=1),
            reference_hash="reference",
            assets=[AssetPlanningState(asset_id="BW-01")],
            baseline_support=support,
        )


def test_new_planner_does_not_import_private_generators():
    assert not audit_consumers(ROOT / "src/twinguard")


def test_unsupported_calibration_cannot_become_healthy(tmp_path, model):
    data = ROOT / "configs/fusion/history"
    captures = sorted(
        [v for v in load_public_observations(data) if isinstance(v, InspectionCapture)],
        key=lambda c: c.acquired_at,
    )
    bundle = copy.deepcopy(model)
    bundle["domains"] = []
    _, g = analyze_geometry(
        data / captures[0].artifact.uri,
        data / captures[1].artifact.uri,
        AnalyticsConfig(),
        load_reference(ROOT / "configs/analytics/accepted_reference.json"),
        tmp_path / "prediction",
        methods=["B3.2"],
        view_calibration=bundle,
    )["B3.2"]
    assert (
        g.status == "inconclusive"
        and g.significant is None
        and not g.regions
        and g.reinspection_candidate
    )
    assert g.measurement_basis == "localized_relative" and g.calibration_id.startswith(
        "uncalibrated"
    )


def test_original_b31_outputs_remain_semantically_identical(tmp_path):
    data = ROOT / "configs/fusion/history"
    original = json.loads((ROOT / "configs/fusion/history/B3.1/geometry.json").read_text())
    captures = sorted(
        [v for v in load_public_observations(data) if isinstance(v, InspectionCapture)],
        key=lambda c: c.acquired_at,
    )
    _, g = analyze_geometry(
        data / captures[0].artifact.uri,
        data / captures[1].artifact.uri,
        AnalyticsConfig(),
        load_reference(ROOT / "configs/analytics/accepted_reference.json"),
        tmp_path / "legacy",
        methods=["B3.1"],
        improved_calibration=json.loads(
            (ROOT / "configs/fusion/calibration/geometry_b31.json").read_text()
        ),
    )["B3.1"]
    current = g.model_dump(mode="json")
    current.pop("runtime_s")
    original.pop("runtime_s")
    assert current == original


def test_p32_missing_baseline_explicitly_has_no_viable_measurement(model):
    cfg = load_config(ROOT / "configs/inspection/planner.yaml")
    surface = ReferenceSurface(ROOT / cfg.reference_path, cfg.reference_sha256, cfg.cell_m)
    snapshot = PlanningSnapshot(
        snapshot_id="unknown",
        at=datetime.now(timezone.utc),
        reference_hash=surface.hash,
        assets=[AssetPlanningState(asset_id="BW-01")],
    )
    output = select_plan(
        surface,
        snapshot,
        cfg,
        InspectionPlanningRequest(request_id="p32", method="P3v2"),
        generate(surface, snapshot, cfg, ROOT),
        model,
        ROOT,
    )
    assert output.status == "no_viable_viewpoint" and not output.steps
    assert output.approval_status == "pending_operator_review"
    assert any(
        "missing_public_baseline_inspection_support" in reasons
        for reasons in output.explanation.rejected.values()
    )


def test_experiment_checkpoint_recovery_never_marks_unexecuted_cases_complete(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("twinguard.evaluation.campaigns.resource_preflight", lambda *a, **k: {})
    path = tmp_path / "campaign"
    campaign = Campaign(path, {"purpose": "controlled-test"})
    campaign.commit("one", {"value": "observed"})
    campaign.fail("controlled interruption")
    assert json.loads((path / "campaign.json").read_text())["status"] == "incomplete"
    resumed = Campaign(path, {"purpose": "controlled-test"}, resume=True)
    with pytest.raises(ValueError):
        resumed.finish(2)
    with pytest.raises(ValueError):
        resumed.commit("one", {"value": "replacement"})
    resumed.commit("two", {"value": "actual second execution"})
    resumed.finish(2)
    state = json.loads((path / "campaign.json").read_text())
    assert (
        state["status"] == "completed"
        and state["resume_history"][0]["prior_status"] == "incomplete"
    )


def test_checkpoint_corruption_or_changed_protocol_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("twinguard.evaluation.campaigns.resource_preflight", lambda *a, **k: {})
    path = tmp_path / "campaign"
    c = Campaign(path, {"version": 1})
    c.commit("one", {"ok": True})
    c.fail("interrupted")
    with pytest.raises(ValueError):
        Campaign(path, {"version": 2}, resume=True)
    (path / "cases/one.json").write_text("{}")
    with pytest.raises(ValueError):
        Campaign(path, {"version": 1}, resume=True)


def test_host_aware_preflight_checks_real_backing_store(monkeypatch):
    import shutil

    original = shutil.disk_usage
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda path: (
            original("/")
            if str(path) == "/"
            else type(original("/"))(100 * 1024**3, 99 * 1024**3, 1024**3)
        ),
    )
    with pytest.raises(RuntimeError, match="host storage preflight"):
        resource_preflight()
