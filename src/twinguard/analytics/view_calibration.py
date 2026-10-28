"""B3.2 view-domain healthy calibration. Only public poses/parameters enter applicability."""

import time
import numpy as np
from .pipeline import fingerprint
from .geometric_improved import detect_improved
from twinguard.core.analytics_contracts import GeometryResult


def pose_distance(left, right):
    a = np.asarray(left.matrix if hasattr(left, "matrix") else left, float)
    b = np.asarray(right.matrix if hasattr(right, "matrix") else right, float)
    return float(np.linalg.norm(a[:3, 3] - b[:3, 3])), float(
        np.arccos(np.clip((np.trace(a[:3, :3].T @ b[:3, :3]) - 1) / 2, -1, 1))
    )


def acquisition_signature(record):
    keys = (
        "channels",
        "horizontal_samples",
        "horizontal_fov_rad",
        "vertical_min_rad",
        "vertical_max_rad",
        "range_sigma_m",
        "range_slope",
        "angular_sigma_rad",
    )
    return {k: record.acquisition_parameters.get(k) for k in keys}


def applicability(baseline_record, current_record, bundle):
    reasons = []
    if "BW-01" not in current_record.asset_ids:
        reasons.append("uncalibrated_target_asset")
    if baseline_record.sensor_pose.target != current_record.sensor_pose.target:
        reasons.append("coordinate_frame_mismatch")
    if baseline_record.sensor_id != current_record.sensor_id:
        reasons.append("sensor_identity_mismatch")
    signature = acquisition_signature(baseline_record)
    if signature != acquisition_signature(current_record):
        reasons.append("baseline_current_sensor_configuration_mismatch")
    decision, domain = planned_applicability(
        baseline_record.sensor_pose, current_record.sensor_pose, signature, bundle
    )
    reasons.extend(decision["reasons"])
    if reasons:
        return {"applicable": False, "reasons": sorted(set(reasons)), "domain_id": None}, None
    return decision, domain


def planned_applicability(baseline_pose, planned_pose, signature, bundle):
    """Predicted domain membership; actual reported capture is independently checked later."""
    domains = []
    for domain in bundle.get("domains", []):
        if domain.get("world_frame") != baseline_pose.target.model_dump(mode="json"):
            continue
        if (
            planned_pose.target != baseline_pose.target
            or planned_pose.source != baseline_pose.source
        ):
            continue
        if domain["sensor_signature"] != signature:
            continue
        bd, ba = pose_distance(baseline_pose, domain["baseline_pose"])
        cd, ca = pose_distance(planned_pose, domain["current_pose"])
        if (
            max(bd, cd) > domain["maximum_pose_distance_m"]
            or max(ba, ca) > domain["maximum_pose_angle_rad"]
        ):
            continue
        if (
            domain["independent_fit_scans"] < 10
            or domain["independent_screen_scans"] < 10
            or not domain["model"].get("multipliers")
        ):
            continue
        domains.append((bd + ba + cd + ca, domain["domain_id"], domain))
    domains.sort(key=lambda v: (v[0], v[1]))
    if not domains:
        return {
            "applicable": False,
            "reasons": ["unsupported_view_or_sensor_calibration_domain"],
            "domain_id": None,
        }, None
    return {"applicable": True, "reasons": [], "domain_id": domains[0][1]}, domains[0][2]


def detect_view_qualified(
    baseline, current, registered_world, registration, reference, config, bundle
):
    started = time.perf_counter()
    if bundle["configuration_sha256"] != fingerprint(config) or bundle[
        "reference_sha256"
    ] != fingerprint(reference):
        raise ValueError("B3.2 calibration/configuration/reference mismatch")
    decision, domain = applicability(baseline.record, current.record, bundle)
    if domain is None:
        return GeometryResult(
            analysis_id="b32-" + current.record.capture_id,
            baseline_capture_id=baseline.record.capture_id,
            current_capture_id=current.record.capture_id,
            acquired_at=current.record.acquired_at,
            method="multiscale_calibrated",
            algorithm_version="v3.2-view-v1",
            registration_id=registration.registration_id,
            reference_id=reference.reference_id,
            calibration_id="uncalibrated-view-domain",
            status="inconclusive",
            asset_statuses={a: "inconclusive" for a in config.monitored_assets},
            patches=[],
            regions=[],
            significant=None,
            sensitivity_statement="Unsupported reported-view/sensor calibration domain; no healthy conclusion",
            measurement_basis="localized_relative",
            reinspection_candidate=True,
            processing_configuration_sha256=fingerprint(config),
            quality_flags=decision["reasons"],
            runtime_s=time.perf_counter() - started,
        )
    result = detect_improved(
        baseline, registered_world, registration, reference, config, domain["model"]
    )
    result = result.model_copy(
        deep=True,
        update={
            "analysis_id": "b32-" + current.record.capture_id,
            "algorithm_version": "v3.2-view-v1",
            "calibration_id": bundle["calibration_id"] + "-" + domain["domain_id"],
            "runtime_s": time.perf_counter() - started,
        },
    )
    result.quality_flags = sorted(
        set(result.quality_flags + ["reported_view_domain_qualified", domain["domain_id"]])
    )
    result.sensitivity_statement += "; view-conditioned healthy calibration; no global/support displacement capability or physical accuracy claim"
    return result
