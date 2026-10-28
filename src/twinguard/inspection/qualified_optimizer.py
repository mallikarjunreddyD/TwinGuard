"""P3v2: engineering measurement-qualified utility; no detection probabilities or labels."""

import numpy as np
import yaml
from twinguard.analytics.view_calibration import planned_applicability
from twinguard.analytics.registration import normal_information
from .visibility import directions
from .coverage import qualified_history
from .contracts import ViewpointUtility
from .optimizer import plan
from .observations import fingerprint

METHOD_VERSION = "p3v2-view-v1"
TARGET_CHANGE_M = (
    0.010  # Declared engineering inspection objective, never a hidden fault amplitude.
)
WEIGHTS = {
    "measurement_area": 0.40,
    "deficiency": 0.25,
    "risk": 0.20,
    "cost": 0.10,
    "redundancy": 0.05,
}


def select_plan(surface, snapshot, config, request, candidates, bundle, root, ablation=None):
    source_snapshot_hash = fingerprint(snapshot)
    for asset, cells in snapshot.required_region_cells.items():
        surface.area_of(cells)
        if any(surface.assets[i] != asset for i in cells):
            raise ValueError("Required-region cells must belong to the declared asset")
    baseline = snapshot.baseline_support
    public_history = qualified_history(surface, snapshot, config)
    support = set(baseline.observed_cells) if baseline else set()
    if baseline:
        surface.area_of(support)
    install = yaml.safe_load((root / config.sensor_path).read_text())
    sensor = install["lidar"]
    signature = {
        k: sensor.get(k)
        for k in (
            "channels",
            "horizontal_samples",
            "horizontal_fov_rad",
            "vertical_min_rad",
            "vertical_max_rad",
        )
    }
    signature.update(
        range_sigma_m=sensor["noise"]["sigma"],
        range_slope=sensor["noise"]["range_slope"],
        angular_sigma_rad=sensor["noise"]["angular_sigma_rad"],
    )
    copies = [v.model_copy(deep=True) for v in candidates]
    predictors = {}
    # Use nominal accepted geometry only to predict registration-normal diversity.
    cell_normal = np.column_stack(
        [
            np.bincount(
                surface.triangle_cell,
                weights=surface.mesh.area_faces * surface.mesh.face_normals[:, j],
                minlength=len(surface.area),
            )
            for j in range(3)
        ]
    )
    norms = np.linalg.norm(cell_normal, axis=1)
    cell_normal = np.divide(
        cell_normal, norms[:, None], out=np.zeros_like(cell_normal), where=norms[:, None] > 1e-12
    )
    for v in copies:
        reasons = []
        domain = None
        common = 0.0
        conditioning = 0.0
        calibration_support = 0.0
        if not baseline:
            reasons.append("missing_public_baseline_inspection_support")
        if v.asset_id not in config.calibrated_assets:
            reasons.append("uncalibrated_target_asset")
        if v.modality != "lidar":
            reasons.append("P3v2_geometric_measurement_model_not_applicable_to_thermal")
        if baseline and v.modality == "lidar":
            decision, domain = planned_applicability(
                baseline.reported_pose, v.planned_pose, signature, bundle
            )
            if not decision["applicable"] and ablation != "no_calibration_applicability":
                reasons.extend(decision["reasons"])
            usable = set(v.predicted_usable_cells)
            common = surface.area_of(usable & support) / max(surface.area_of(usable), 1e-12)
            matrix = np.asarray(v.planned_pose.matrix)
            distance, _, cells = surface.cast(
                matrix[:3, 3], directions(sensor, "lidar") @ matrix[:3, :3].T
            )
            ids = np.unique(cells[np.isfinite(distance)])
            if len(ids) >= 6:
                conditioning = float(normal_information(surface.centers[ids], cell_normal[ids]))
            if conditioning < 1e-5 and ablation != "no_registration_suitability":
                reasons.append("predicted_registration_normal_geometry_unsupported")
            calibration_support = (
                min(
                    1, domain["independent_fit_scans"] / 15, domain["independent_screen_scans"] / 15
                )
                if domain
                else float(ablation == "no_calibration_applicability")
            )
        sensitivity = 0.0
        if domain:
            group = signature.get("range_sigma_m")
            group = format(group, ".6g") if isinstance(group, (float, int)) else "unknown"
            scales = [v["scale_m"] for v in domain["model"]["maps"].get(group, {}).values()]
            multiplier = domain["model"]["multipliers"].get(group)
            if scales and multiplier is not None:
                envelope = domain["model"]["minimum_effect_m"] + multiplier * float(
                    np.median(scales)
                )
                sensitivity = min(1.0, TARGET_CHANGE_M / max(2 * envelope, 1e-12))
        elif ablation == "no_calibration_applicability":
            sensitivity = 1.0
        quality = (
            v.expected_quality
            * min(1, 0.16 / max(v.predicted_spacing_m, 1e-9))
            * common
            * calibration_support
            * sensitivity
        )
        if ablation != "no_registration_suitability":
            quality *= min(1, conditioning / 1e-4)
        if reasons and v.feasibility.status == "feasible":
            v.feasibility.status = "infeasible"
            v.feasibility.reasons += reasons
        v.assumptions += [
            "P3v2 engineering suitability is not a probability of fault detection",
            "Predicted view-domain membership must be rechecked on actual reported acquisition",
        ]
        predictors[v.viewpoint_id] = {
            "engineering_measurement_suitability": quality,
            "baseline_common_area_fraction": common,
            "predicted_normal_conditioning": conditioning,
            "healthy_domain_support": calibration_support,
            "engineering_sensitivity_proxy": sensitivity,
            "domain_id": domain["domain_id"] if domain else None,
        }
    if ablation == "no_coverage_history":
        snapshot = snapshot.model_copy(deep=True, update={"coverage": []})

    def score(v, covered, surface, priority, config, travel_s, budget_s):
        usable = set(v.predicted_usable_cells)
        new = usable - covered
        target = set(snapshot.required_region_cells.get(v.asset_id, []))
        if target:
            new &= target
            total = surface.area_of(target)
        else:
            total = float(surface.area[surface.assets == v.asset_id].sum())
        fraction = surface.area_of(new) / max(total, 1e-12)
        q = predictors[v.viewpoint_id]["engineering_measurement_suitability"]
        measurement = fraction * q
        terms = {
            "measurement_area": measurement,
            "deficiency": measurement * priority.terms["deficiency"],
            "risk": measurement * priority.score if ablation != "no_risk_priority" else 0.0,
            "cost": min(1, (travel_s + v.acquisition_s) / budget_s),
            "redundancy": (1 - len(new) / max(1, len(usable)))
            if ablation != "no_redundancy_penalty"
            else 0.0,
            "common_baseline_area": predictors[v.viewpoint_id]["baseline_common_area_fraction"],
            "conditioning_proxy": predictors[v.viewpoint_id]["predicted_normal_conditioning"],
            "calibration_support": predictors[v.viewpoint_id]["healthy_domain_support"],
            "sensitivity_proxy": predictors[v.viewpoint_id]["engineering_sensitivity_proxy"],
        }
        value = sum(
            WEIGHTS[k] * terms[k] * (-1 if k in ("cost", "redundancy") else 1) for k in WEIGHTS
        )
        return ViewpointUtility(score=value, terms=terms, new_cells=sorted(new))

    result = plan(surface, snapshot, config, request, copies, scorer=score)
    policy = {
        "planner_version": METHOD_VERSION,
        "base_configuration": fingerprint(config),
        "view_calibration": fingerprint(bundle),
        "weights": WEIGHTS,
        "target_change_m": TARGET_CHANGE_M,
        "ablation": ablation,
    }
    result.snapshot_hash = source_snapshot_hash
    result.policy_hash = fingerprint(policy)
    result.plan_id = (
        "plan-" + fingerprint([source_snapshot_hash, request.model_dump(mode="json"), policy])[:24]
    )
    result.explanation.limitations += [
        "P3v2 " + METHOD_VERSION + "; weights " + str(WEIGHTS),
        "No oracle localization or calibrated fault-detection probability; scoped coverage does not establish whole-asset health",
    ]
    targets = {i for ids in snapshot.required_region_cells.values() for i in ids}
    if targets and targets <= public_history and not result.steps:
        result.status = "continue_monitoring"
        result.explanation.recommended_actions = [
            "Configured measured geometric region has recent qualified coverage; other unknown hazards remain unknown"
        ]
    return result
