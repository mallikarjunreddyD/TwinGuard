from pathlib import Path
from datetime import timedelta
import numpy as np
import pytest
from pydantic import ValidationError
from twinguard.fusion.models import ProcessingRecord, FusionState, OperatorAction
from twinguard.fusion.policies import load_policy, policy_hash
from twinguard.fusion.engine import assess, replay
from twinguard.fusion.temporal import validate
from twinguard.fusion.spatial import compatible
from twinguard.fusion.dependence import relationship
from twinguard.fusion import adapters
from twinguard.fusion.io import save_evidence, read_evidence
from twinguard.evaluation.fusion_scenarios import controlled, evidence, START
from twinguard.core.analytics_contracts import ThermalResult, OperatingPrediction
from twinguard.core.contracts import SensorObservation
from twinguard.core.boundaries import audit_consumers
from test_phase3_units import capture, reference, valid_registration
from twinguard.analytics.clouds import preprocess
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.geometry import detect_geometry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def policy():
    return load_policy(ROOT / "configs/fusion/hazards.yaml")


def processing(source, t=0, clock="synchronized"):
    return ProcessingRecord(
        source_id=source,
        received_at=START + timedelta(seconds=t + 0.1),
        processed_at=START + timedelta(seconds=t + 0.2),
        available_at=START + timedelta(seconds=t + 0.2),
        basis="simulated_replay",
        rationale="Explicit unit-test replay timing",
        clock_quality=clock,
    )


def observation(value=1e6, quality="good", sensor="pressure-01"):
    return SensorObservation(
        observation_id="o1",
        sensor_id=sensor,
        asset_id="BW-01",
        acquired_at=START,
        received_at=START + timedelta(seconds=0.1),
        measurement_type="pressure",
        value=value,
        unit="Pa",
        quality=quality,
        provenance_id="unit-public",
        location_reference="BW-01",
    )


@pytest.mark.parametrize("case", range(1, 23))
def test_controlled_policy_properties(policy, case):
    e, actions, p, at, label = controlled(case, 2, policy)
    state, history = replay(e, p, at, actions)
    final = [d for d in history if d.assessment.asset_id == label["target_asset"]][-1]
    assert final.assessment.severity == label["expected_severity"]
    assert final.policy_sha256 == policy_hash(p) and final.rationale
    assert final.assessment.confidence_status in ["supported", "limited", "insufficient", "unknown"]
    if case == 5:
        assert "pressure-monitoring" not in final.missing_requirements
    if case in [5, 6, 7, 13]:
        assert final.assessment.severity == "red" and final.positive_ids
    if case == 8:
        assert "coincident-structural-thermal" in final.triggered_hazards
    if case == 9:
        assert "coincident-structural-thermal" not in final.triggered_hazards
    if case == 12:
        assert "local-wall-inspection" in final.missing_requirements
    if case == 19:
        assert any(
            e.lifecycle == "resolved" and e.hazard_id == "critical-pressure"
            for e in state.events.values()
        )
    if case == 20:
        assert any(
            e.lifecycle == "acknowledged" and e.hazard_id == "critical-pressure"
            for e in state.events.values()
        )
    if case == 22:
        assert any(n.transition == "monitoring_unavailable" for n in state.notices)


@pytest.mark.parametrize(
    "value,quality,sensor,expected",
    [
        (1.3e6, "good", "pressure-01", "positive"),
        (1e6, "good", "pressure-01", "negative"),
        (3e6, "good", "pressure-01", "inconclusive"),
        (1.3e6, "invalid", "pressure-01", "invalid"),
        (1.3e6, "good", "unknown", "inconclusive"),
    ],
)
def test_raw_limit_adapter(policy, value, quality, sensor, expected):
    source = observation(value, quality, sensor)
    e = adapters.engineering_limit(source, processing(source.observation_id), policy)
    assert e.finding == expected
    if expected == "positive":
        assert e.authoritative_limit
    if expected == "negative":
        assert e.recovery_eligible


def test_unconfigured_limit_and_calibration(policy):
    site = load_policy(ROOT / "configs/fusion/site-template.yaml")
    source = observation(1.3e6)
    e = adapters.engineering_limit(source, processing("o1"), site)
    assert e.finding == "inconclusive" and not e.authoritative_limit
    assert any("unconfigured" in r for r in e.reasons)
    raw = policy.model_dump()
    raw["authorities"][0]["calibration_status"] = "expired"
    expired = policy.model_validate(raw)
    source = SensorObservation.model_validate(
        {
            **observation().model_dump(),
            "sensor_id": "temperature-01",
            "measurement_type": "temperature",
            "unit": "degC",
            "value": 200,
        }
    )
    e = adapters.engineering_limit(source, processing("o1"), expired)
    assert e.finding == "inconclusive"


def test_operating_residual_is_not_critical_and_lineage(policy):
    source = observation(1.1e6)
    p = OperatingPrediction(
        prediction_id="prediction",
        observation_id=source.observation_id,
        sensor_id=source.sensor_id,
        asset_id=source.asset_id,
        acquired_at=START,
        available_at=START + timedelta(seconds=0.1),
        model_id="healthy-model",
        method="conditioned_quality",
        observed_value=source.value,
        estimated_reference=1e6,
        residual=1e5,
        uncertainty_score=500,
        threshold=2500,
        unit="Pa",
        significant=True,
        status="valid",
        quality_flags=[],
    )
    residual = adapters.operating(p, source, processing(p.prediction_id))
    limit = adapters.engineering_limit(source, processing(source.observation_id), policy)
    assert residual.finding == "positive" and not residual.authoritative_limit
    assert limit.finding == "negative"
    assert relationship(residual, limit, policy).status == "dependent"
    with pytest.raises(ValueError):
        adapters.operating(p, source.model_copy(update={"value": 1}), processing(p.prediction_id))


@pytest.fixture
def geometric():
    x, z = np.meshgrid(np.linspace(-0.9, 0.9, 60), np.linspace(0.2, 2.8, 70))
    points = np.column_stack([x.ravel(), np.zeros(x.size), z.ravel()])
    b = preprocess(points, capture(), AnalyticsConfig())
    r = valid_registration(b.record)
    current = b.processing_world_m.copy()
    radius = (current[:, 0] / 0.4) ** 2 + ((current[:, 2] - 1.5) / 0.5) ** 2
    current[:, 1] += 0.03 * np.maximum(0, 1 - radius) ** 3
    g = detect_geometry(
        b,
        current,
        r,
        reference(),
        AnalyticsConfig(uncertainty_floor_m=0.001),
        {
            "calibration_id": "healthy-calibration",
            "uncertainty_floor_m": 0.001,
            "threshold_m": 0.005,
        },
    )
    return g, r


def test_actual_geometry_adapter_and_unqualified_patch(geometric):
    g, r = geometric
    # Fixture capture timestamp is START; bind current ID according to the public registration.
    g = g.model_copy(
        update={
            "current_capture_id": r.current_capture_id,
            "measurement_basis": "localized_relative",
            "method": "multiscale_calibrated",
            "algorithm_version": "v3.1",
        }
    )
    g.patches = [p.model_copy(update={"calibration_support": 20}) for p in g.patches]
    pr = processing(g.analysis_id)
    outputs = adapters.geometry(g, r, pr, "fixture")
    assert any(
        e.finding == "positive" and e.measurement_basis == "localized_relative" for e in outputs
    )
    bad = g.model_copy(deep=True)
    for p in bad.patches:
        p.calibration_support = 0
    assert not any(e.finding == "positive" for e in adapters.geometry(bad, r, pr, "fixture"))
    failed = r.model_copy(update={"status": "inconclusive"})
    assert all(e.finding == "unavailable" for e in adapters.geometry(g, failed, pr, "fixture"))
    l2 = g.model_copy(
        update={
            "status": "insufficient_coverage",
            "asset_statuses": {"BW-01": "insufficient_coverage"},
        }
    )
    assert all(e.finding == "inconclusive" for e in adapters.geometry(l2, r, pr, "fixture"))


def test_thermal_image_only_and_saturation():
    raw = dict(
        analysis_id="thermal-analysis",
        capture_id="thermal-capture",
        acquired_at=START,
        model_id="healthy-template",
        method="conditioned",
        status="valid",
        valid_pixels=100,
        saturated_pixels=0,
        total_pixels=100,
        saturation_known=True,
        regions=[
            dict(
                region_id="hotspot",
                image_bounds=(1, 1, 5, 5),
                pixel_count=16,
                asset_id=None,
                association_status="image_only",
                peak_residual_c=10,
                median_residual_c=8,
                uncertainty_score_c=0.5,
            )
        ],
        significant=True,
        quality_flags=[],
    )
    result = ThermalResult.model_validate(raw)
    e = adapters.thermal(result, processing(result.analysis_id), "fixture")[0]
    assert e.asset_id is None and e.association == "image_only" and not e.region_comparison_possible
    raw.update(
        status="inconclusive", valid_pixels=0, saturated_pixels=100, regions=[], significant=None
    )
    result = ThermalResult.model_validate(raw)
    e = adapters.thermal(result, processing(result.analysis_id), "fixture")[0]
    assert e.finding == "inconclusive" and e.quality_indicators["saturated_pixels"] == 100


@pytest.mark.parametrize(
    "kind,status",
    [
        ("stale", "stale"),
        ("future", "future"),
        ("clock", "clock_unknown"),
        ("processing", "not_available"),
    ],
)
def test_temporal_edges(policy, kind, status):
    e = evidence(
        "time-test",
        "pressure",
        "positive",
        t=-20 if kind == "stale" else 50 if kind == "future" else 0,
        delay=30 if kind == "processing" else 0.2,
        clock_quality="unknown" if kind == "clock" else "synchronized",
    )
    result = validate(e, policy.rules[0], START + timedelta(seconds=5), policy)
    assert result.status == status and not result.applicable


@pytest.mark.parametrize(
    "change,expected",
    [
        ({}, "compatible"),
        ({"asset_id": "DR-01"}, "incompatible"),
        ({"association": "image_only", "region_comparison_possible": False}, "unknown"),
        ({"spatial_reference": "other-frame"}, "incompatible"),
        ({"bounds_world_m": ((3, 0, 0), (4, 1, 1))}, "incompatible"),
    ],
)
def test_spatial_regions(change, expected):
    a = evidence(
        "a",
        "geometry",
        "positive",
        bounds_world_m=((0, 0, 0), (1, 1, 1)),
        region_comparison_possible=True,
        spatial_reference="plant-01",
    )
    b = evidence(
        "b",
        "thermal",
        "positive",
        bounds_world_m=((0.9, 0, 0), (1.5, 1, 1)),
        region_comparison_possible=True,
        spatial_reference="plant-01",
    ).model_copy(update=change)
    assert compatible(a, b, "region", 0.05).status == expected


def test_dependence_algorithms_shared_context_and_independent(policy):
    a = evidence("a", "geometry", "positive")
    b = a.model_copy(update={"evidence_id": "b", "algorithm": "patch_screening"})
    assert relationship(a, b, policy).status == "dependent"
    c = evidence("c", "thermal", "positive")
    assert relationship(a, c, policy).status == "independent"
    assert (
        relationship(
            a.model_copy(update={"shared_references": ["common"]}),
            c.model_copy(update={"shared_references": ["common"]}),
            policy,
        ).status
        == "dependent"
    )


def test_checkpoint_replay_and_expiry_no_recovery(policy):
    e, actions, p, at, label = controlled(5, 1, policy)
    state, history = replay(e, p, at)
    checkpoint = FusionState.model_validate_json(state.model_dump_json())
    later = at + timedelta(hours=2)
    resumed, decisions = assess(checkpoint, [], p, later)
    wall = next(d for d in decisions if d.assessment.asset_id == "BW-01")
    assert wall.assessment.severity == "red"
    assert any(
        ev.monitoring_unavailable
        for ev in resumed.events.values()
        if ev.hazard_id == "critical-pressure"
    )
    with pytest.raises(ValueError, match="backward"):
        assess(resumed, [], p, at)
    state2, history2 = replay(e, p, at)
    assert state2.model_dump() == state.model_dump() and [h.model_dump() for h in history2] == [
        h.model_dump() for h in history
    ]
    dup, _ = assess(state, [e[-1]], p, at)
    assert len(dup.notices) == len(state.notices)


def test_repair_invalidates_geometry_and_ack_is_not_recovery(policy):
    e, _, p, at, _ = controlled(2, 1, policy)
    repair = OperatorAction(
        action_id="repair",
        asset_id="BW-01",
        at=START + timedelta(seconds=3),
        kind="repair",
        rationale="Recorded authorized repair",
    )
    state, h = replay(e, p, at, [repair])
    assert any(t.status == "historical_repaired" for d in h for t in d.temporal)
    assert any(
        x.lifecycle == "resolved"
        for x in state.events.values()
        if x.hazard_id == "localized-geometry"
    )


def test_public_manifest_hash_and_truth_isolation(policy, tmp_path, monkeypatch):
    e, _, p, at, _ = controlled(5, 1, policy)
    save_evidence(tmp_path / "evidence", e, {"kind": "unit"})
    original = Path.read_text

    def read(path, *args, **kwargs):
        assert "evaluation_private" not in path.parts
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scope:
        scope.setattr(Path, "read_text", read)
        replay(read_evidence(tmp_path / "evidence"), p, at)
    assert audit_consumers(ROOT / "src/twinguard") == []
    (tmp_path / "evidence/evidence.json").write_text("[]")
    with pytest.raises(ValueError, match="checksum"):
        read_evidence(tmp_path / "evidence")


def test_contract_policy_validation(policy):
    with pytest.raises(ValidationError):
        processing("x").model_copy(update={"available_at": START}).model_validate(
            {**processing("x").model_dump(), "available_at": START}
        )
    raw = policy.model_dump()
    raw["authorities"][1]["engineering_basis"] = None
    with pytest.raises(ValidationError):
        policy.model_validate(raw)


def test_f0_one_two_three_modalities(policy):
    records = [
        evidence("pressure-positive", "pressure", "positive", 1),
        evidence("geometry-positive", "geometry", "positive", 1),
        evidence("thermal-positive", "thermal", "positive", 1),
    ]
    for count, expected in [(1, "unknown"), (2, "amber"), (3, "red")]:
        _, history = replay(records[:count], policy, START + timedelta(seconds=3), method="F0")
        assert [d for d in history if d.assessment.asset_id == "BW-01"][
            -1
        ].assessment.severity == expected


def test_hysteresis_and_candidate_duration(policy):
    source = observation(1140000)
    limit = adapters.engineering_limit(source, processing("o1"), policy)
    assert limit.finding == "negative" and not limit.recovery_eligible
    custom = policy.model_copy(deep=True)
    rule = next(r for r in custom.rules if r.hazard_id == "residual-pressure")
    rule.min_positive_count = 2
    rule.min_duration_s = 2
    first = evidence("first", "residual", "positive", 1)
    duplicate = first.model_copy(
        update={"evidence_id": "derived-same-time", "source_id": "derived-same-time"}
    )
    state, h = replay([first, duplicate], custom, START + timedelta(seconds=2))
    assert (
        next(e for e in state.events.values() if e.hazard_id == "residual-pressure").lifecycle
        == "candidate"
    )
    second = evidence("second", "residual", "positive", 4)
    state, h = replay([second], custom, START + timedelta(seconds=5), state=state)
    assert (
        next(e for e in state.events.values() if e.hazard_id == "residual-pressure").lifecycle
        == "active"
    )


def test_no_retroactive_availability_and_checkpoint_method(policy):
    delayed = evidence("delayed", "pressure", "positive", 1, delay=4)
    state, h = replay(
        [delayed], policy, START + timedelta(seconds=3), timeline=[START + timedelta(seconds=3)]
    )
    assert not any(d.assessment.severity == "red" for d in h)
    state, h = replay([delayed], policy, START + timedelta(seconds=6), state=state)
    assert any(d.assessment.severity == "red" for d in h)
    with pytest.raises(ValueError, match="method"):
        assess(state, [], policy, START + timedelta(seconds=7), method="F0")


def test_single_critical_despite_uncalibrated_reference(policy):
    critical = evidence("critical-only", "pressure", "positive", 1)
    model = evidence("model-unavailable", "residual", "inconclusive", 1)
    _, h = replay([critical, model], policy, START + timedelta(seconds=3))
    wall = [d for d in h if d.assessment.asset_id == "BW-01"][-1]
    assert wall.assessment.severity == "red" and wall.assessment.confidence_status == "limited"
    assert wall.missing_requirements


def test_qualified_candidate_is_covered_but_not_green(policy):
    records, actions, p, at, _ = controlled(4, 4, policy)
    rule = next(r for r in p.rules if r.hazard_id == "residual-pressure")
    rule.min_positive_count = 2
    rule.min_duration_s = 2
    _, history = replay(records, p, at, actions)
    wall = [d for d in history if d.assessment.asset_id == "BW-01"][-1]
    assert wall.assessment.severity == "unknown"
    assert "operating-pressure-coverage" not in wall.missing_requirements
    assert any("await applicable activation" in reason for reason in wall.rationale)
