"""Numerical B3.1 validation; no precomputed benchmark success assertions."""

from pathlib import Path
import json
import numpy as np
import pytest
from test_phase3_units import capture, reference, valid_registration
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.clouds import preprocess
from twinguard.analytics.geometric_improved import calibrate, detect_improved, cluster_score
from twinguard.analytics.pipeline import analyze_geometry
from twinguard.core.boundaries import audit_consumers
from twinguard.evaluation.geometric_studies import generate


@pytest.fixture(scope="module")
def calibrated():
    x, z = np.meshgrid(np.linspace(-0.9, 0.9, 65), np.linspace(0.2, 2.8, 81))
    points = np.column_stack([x.ravel(), np.zeros(x.size), z.ravel()])
    config = AnalyticsConfig()
    b = preprocess(points, capture(), config)
    reg = valid_registration(b.record)
    rng = np.random.default_rng(12001)
    samples = []
    for i in range(24):
        current = b.processing_world_m.copy()
        current[:, 1] += rng.normal(0, 0.0003, len(current))
        samples.append((b, current, reg, i < 12))
    model = calibrate(samples, config, reference(), [f"healthy-{i}" for i in range(24)])
    return b, reg, config, model


@pytest.mark.parametrize("amplitude", [0.01, 0.02, 0.03])
def test_gaussian_localized_displacement_and_margin(calibrated, amplitude):
    b, reg, config, model = calibrated
    current = b.processing_world_m.copy()
    gaussian = np.exp(-0.5 * ((current[:, 0] / 0.14) ** 2 + ((current[:, 2] - 1.5) / 0.16) ** 2))
    current[:, 1] += amplitude * gaussian
    result = detect_improved(b, current, reg, reference(), config, model)
    assert result.significant is True and result.measurement_basis == "localized_relative"
    assert len(result.regions) > 0
    assert max(p.displacement_m or 0 for p in result.patches) > 0.5 * amplitude
    for patch in result.patches:
        if patch.status != "valid":
            continue
        expected = (
            abs(patch.displacement_m)
            - patch.threshold_m
            - model["multipliers"]["0"] * patch.uncertainty_score_m
        )
        assert patch.engineering_margin_m == pytest.approx(expected)
        assert patch.scale_m in [0.08, 0.12] and patch.direction == "oriented"


def test_healthy_and_uniform_shift_are_explicitly_relative(calibrated):
    b, reg, config, model = calibrated
    for shift in [0, 0.02]:
        current = b.processing_world_m.copy()
        current[:, 1] += shift
        result = detect_improved(b, current, reg, reference(), config, model)
        assert result.significant is False
        assert result.measurement_basis == "localized_relative"
        assert "does not establish health" in result.sensitivity_statement


def test_sparse_invalid_and_calibration_mismatch(calibrated):
    b, reg, config, model = calibrated
    missing = detect_improved(b, np.empty((0, 3)), reg, reference(), config, model)
    assert missing.status == "insufficient_coverage" and missing.significant is None
    assert (
        missing.reinspection_candidate
        and missing.asset_statuses["SUP-01"] == "insufficient_coverage"
    )
    invalid = detect_improved(
        b,
        b.processing_world_m,
        reg.model_copy(update={"status": "inconclusive"}),
        reference(),
        config,
        model,
    )
    assert invalid.significant is None
    with pytest.raises(ValueError, match="mismatch"):
        detect_improved(
            b,
            b.processing_world_m,
            reg,
            reference(),
            config.model_copy(update={"patch_spacing_m": 0.1}),
            model,
        )


def test_spatial_cluster_rule_excludes_isolated_extremum():
    p = np.array([[0, 0, 0], [0.12, 0, 0], [2, 0, 0]])
    assert cluster_score(p, np.array([2, 3, 100]), 0.12) == 2
    assert cluster_score(p[:1], np.array([100]), 0.12) == 0


def test_partition_disjointness_and_original_source_checkpoint():
    root = Path(__file__).resolve().parents[1]
    partitions = json.loads((root / "configs/experiments/phase3_1/partitions.json").read_text())
    sets = [
        set(partitions[k])
        for k in [
            "diagnostic_seeds",
            "development_seeds",
            "healthy_calibration_seeds",
            "heldout_seeds",
        ]
    ]
    assert all(not a & b for i, a in enumerate(sets) for b in sets[i + 1 :])
    assert audit_consumers(root / "src/twinguard") == []
    import hashlib

    frozen = json.loads((root / "docs/phase3_1/root_cause_checkpoint.json").read_text())
    for name in ["src/twinguard/analytics/geometry.py", "src/twinguard/analytics/registration.py"]:
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == frozen["files"][name]


def test_b31_public_only_and_original_selectable(monkeypatch, tmp_path, calibrated):
    root = Path(__file__).resolve().parents[1]
    data = tmp_path / "data"
    paths = generate(root, data, "public-only", 12999, "L0", 0.01, "same")
    from twinguard.analytics.reference import load_reference
    from twinguard.analytics.pipeline import fingerprint

    # Plane calibration is only a structural fixture here; no benchmark accuracy assertion.
    _, _, config, original = calibrated
    model = dict(original)
    ref = load_reference(root / "configs/analytics/accepted_reference.json")
    model["reference_sha256"] = fingerprint(ref)
    read_text = Path.read_text
    np_load = np.load

    def protected(path, *args, **kwargs):
        assert "evaluation_private" not in Path(path).parts
        return read_text(path, *args, **kwargs)

    def public_arrays(path, *args, **kwargs):
        if isinstance(path, (str, Path)):
            assert "evaluation_private" not in Path(path).parts
        return np_load(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "read_text", protected)
        context.setattr(np, "load", public_arrays)
        result = analyze_geometry(
            *paths,
            config,
            ref,
            tmp_path / "predictions",
            methods=["B3", "B3.1"],
            improved_calibration=model,
        )
    assert set(result) == {"B3", "B3.1"}
    assert result["B3"][1].method == "patch_screening"
    assert result["B3.1"][1].algorithm_version == "v3.1"


def test_stable_box_pose_error_and_partial_overlap():
    from twinguard.analytics.registration import register
    from twinguard.analytics.reference import AcceptedReference, ReferenceAsset

    rng = np.random.default_rng(553)
    points = rng.uniform(-0.5, 0.5, (2200, 3))
    axis = rng.integers(0, 3, len(points))
    points[np.arange(len(points)), axis] = rng.choice([-0.5, 0.5], len(points))
    points += [0, 0, 1.5]
    config = AnalyticsConfig(monitored_assets=[])
    ref = AcceptedReference(
        reference_id="box-reference",
        provenance="measured synthetic fixture",
        assets=[
            ReferenceAsset(asset_id="REF-01", bounds_world_m=((-1, -1, 0), (1, 1, 3)), stable=True)
        ],
    )
    b = preprocess(points, capture("b"), config)
    pose = np.eye(4)
    pose[:3, 3] = [0.015, -0.008, 0.01]
    c = preprocess(points[points[:, 0] > -0.25], capture("c", pose.tolist()), config)
    result, registered = register(b, c, config, ref)
    assert result.status == "valid" and "stable_reference_fallback" not in result.quality_flags
    assert np.linalg.norm(np.asarray(result.transform.matrix)[:3, 3]) < 0.003
    assert len(registered) > 500


def test_tubular_estimator_and_opposite_surface_qualification():
    from twinguard.analytics.geometry import detect_geometry

    x, z = np.meshgrid(np.linspace(-0.85, 0.85, 180), np.linspace(0.2, 2.8, 60))
    local = (x + 0.055) % 0.11 - 0.055
    y = -0.065 + np.sqrt(np.maximum(0.065**2 - local**2, 0))
    points = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    config = AnalyticsConfig(patch_radius_m=0.08)
    b = preprocess(points, capture(), config)
    reg = valid_registration(b.record)
    current = b.processing_world_m.copy()
    r = (current[:, 0] / 0.4) ** 2 + ((current[:, 2] - 1.5) / 0.5) ** 2
    current[:, 1] += 0.02 * np.maximum(0, 1 - r) ** 3
    result = detect_geometry(b, current, reg, reference(), config)
    assert max(p.displacement_m or 0 for p in result.patches) > 0.012
    assert all(p.normal_world[1] > 0 for p in result.patches if p.direction == "oriented")
    opposing = np.concatenate([current, current + [0, -0.07, 0]])
    ambiguous = detect_geometry(b, opposing, reg, reference(), config)
    assert any(p.status != "valid" for p in ambiguous.patches)
