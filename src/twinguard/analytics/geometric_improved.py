"""B3.1 localized relative change, calibrated from measured healthy observations only."""

import time
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from .geometry import detect_geometry, robust_scale
from .pipeline import fingerprint
from twinguard.core.analytics_contracts import GeometryRegion


SCALES = (0.08, 0.12)


def noise_group(record):
    # Public acquisition parameters, never a scenario/fault label.
    return format(record.acquisition_parameters.get("range_sigma_m", 0), ".6g")


def detrend(patches):
    """Robust wall-relative offset/tilt; never a claim of absolute displacement."""
    valid = [
        p
        for p in patches
        if p.status == "valid" and p.direction == "oriented" and p.asset_id == "BW-01"
    ]
    if len(valid) < 30:
        return {}, None
    xyz = np.array([p.center_world_m for p in valid])
    y = np.array([p.displacement_m for p in valid])
    if np.ptp(xyz[:, 0]) < 0.6 or np.ptp(xyz[:, 2]) < 0.6:
        return {}, None
    x = np.column_stack([np.ones(len(xyz)), xyz[:, 0], xyz[:, 2] - 1.5])
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    for _ in range(12):
        residual = y - x @ beta
        scale = max(robust_scale(residual), 0.0005)
        weight = np.minimum(1, 1.5 * scale / np.maximum(np.abs(residual), 1e-12))
        beta = np.linalg.lstsq(x * weight[:, None], y * weight, rcond=None)[0]
    return {p.patch_id: float(v) for p, v in zip(valid, y - x @ beta)}, beta.tolist()


def measurements(baseline, current, registration, reference, config):
    results = []
    for radius in SCALES:
        local = config.model_copy(update={"patch_radius_m": radius})
        result = detect_geometry(baseline, current, registration, reference, local)
        relative, beta = detrend(result.patches)
        values = {}
        for p in result.patches:
            if p.patch_id in relative:
                values[p.patch_id] = relative[p.patch_id]
        results.append((radius, result, values, beta))
    return results


def cluster_score(points, scores, spacing):
    """Largest neighboring pair's weaker score; handles correlated patch multiplicity."""
    if len(points) < 2:
        return 0.0
    pairs = cKDTree(points).query_pairs(spacing * 1.8)
    return max((min(scores[i], scores[j]) for i, j in pairs), default=0.0)


def calibrate(samples, config, reference, training_ids):
    """Samples supply only public scans, estimated registration and a fit/screen split."""
    cache = []
    groups = {}
    for baseline, current, registration, fit in samples:
        group = noise_group(baseline.record)
        measured = measurements(baseline, current, registration, reference, config)
        cache.append((group, measured, fit))
        if not fit:
            continue
        for radius, _, values, _ in measured:
            for key, value in values.items():
                groups.setdefault(group, {}).setdefault(f"{radius}:{key}", []).append(value)
    maps = {}
    for group, values in groups.items():
        maps[group] = {}
        for key, v in values.items():
            if len(v) < 10:
                continue
            bias = float(np.median(v))
            scale = max(0.0005, float(np.quantile(np.abs(np.array(v) - bias), 0.9)))
            maps[group][key] = {"bias_m": bias, "scale_m": scale, "samples": len(v)}
    maxima = {group: [] for group in maps}
    for group, measured, fit in cache:
        if fit:
            continue
        # At each spatial center choose the strongest supported scale. Calibrate this exact selection.
        candidates = {}
        for radius, result, values, _ in measured:
            for p in result.patches:
                key = f"{radius}:{p.patch_id}"
                model = maps.get(group, {}).get(key)
                if model is None or p.patch_id not in values:
                    continue
                score = (abs(values[p.patch_id] - model["bias_m"]) - 0.002) / model["scale_m"]
                previous = candidates.get(p.patch_id)
                if previous is None or score > previous[1]:
                    candidates[p.patch_id] = (p.center_world_m, score)
        values = list(candidates.values())
        if len(values) >= 30:
            maxima.setdefault(group, []).append(
                cluster_score(
                    np.array([v[0] for v in values]),
                    np.array([v[1] for v in values]),
                    config.patch_spacing_m,
                )
            )
    multipliers = {
        g: max(1.5, float(np.quantile(v, 0.95))) for g, v in maxima.items() if len(v) >= 10
    }
    model = {
        "calibration_id": "b31-" + fingerprint(training_ids)[:16],
        "algorithm_version": "v3.1",
        "training_datasets": training_ids,
        "configuration_sha256": fingerprint(config),
        "reference_sha256": fingerprint(reference),
        "scales_m": list(SCALES),
        "minimum_effect_m": 0.002,
        "maps": maps,
        "multipliers": multipliers,
        "healthy_screen_cluster_maxima": maxima,
        "interpretation": "engineering screening; spatially dependent scan/cluster maxima, not a statistical confidence interval",
        "measurement_basis": "localized_relative",
    }
    return model


def detect_improved(baseline, current, registration, reference, config, calibration):
    started = time.perf_counter()
    if calibration["configuration_sha256"] != fingerprint(config) or calibration[
        "reference_sha256"
    ] != fingerprint(reference):
        raise ValueError("B3.1 frozen calibration/configuration/reference mismatch")
    group = noise_group(baseline.record)
    models = calibration["maps"].get(group, {})
    multiplier = calibration["multipliers"].get(group)
    measured = measurements(baseline, current, registration, reference, config)
    choices = {}
    rejected = {}
    for radius, result, values, beta in measured:
        for p in result.patches:
            key = f"{radius}:{p.patch_id}"
            model = models.get(key)
            if model is None or p.patch_id not in values or multiplier is None:
                rejected.setdefault(
                    p.patch_id,
                    p.model_copy(
                        update={
                            "status": "inconclusive",
                            "significant": None,
                            "quality_flags": sorted(
                                set(
                                    p.quality_flags
                                    + ["no_qualified_local_calibration_or_common_mode"]
                                )
                            ),
                        }
                    ),
                )
                continue
            value = values[p.patch_id] - model["bias_m"]
            scale = model["scale_m"]
            margin = abs(value) - calibration["minimum_effect_m"] - multiplier * scale
            revised = p.model_copy(
                update={
                    "displacement_m": value,
                    "raw_displacement_m": p.displacement_m,
                    "uncertainty_score_m": scale,
                    "engineering_margin_m": margin,
                    "threshold_m": calibration["minimum_effect_m"],
                    "significant": bool(margin > 0),
                    "scale_m": radius,
                    "calibration_support": model["samples"],
                    "registration_component_m": float(p.displacement_m - values[p.patch_id]),
                    "quality_flags": [
                        "localized_relative_common_mode_removed",
                        "empirical_healthy_cluster_screen",
                    ],
                }
            )
            # Compare normalized margins consistently with the calibration scale-selection rule.
            priority = (abs(value) - calibration["minimum_effect_m"]) / scale
            if p.patch_id not in choices or priority > choices[p.patch_id][0]:
                choices[p.patch_id] = (priority, revised)
    patches = [
        choices[key][1] if key in choices else rejected[key]
        for key in sorted(set(choices) | set(rejected))
    ]
    significant = [p for p in patches if p.significant]
    regions = []
    if significant:
        points = np.array([p.center_world_m for p in significant])
        pairs = cKDTree(points).query_pairs(config.patch_spacing_m * 1.8)
        rows = []
        cols = []
        for i, j in pairs:
            if significant[i].asset_id == significant[j].asset_id:
                rows.extend([i, j])
                cols.extend([j, i])
        graph = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(points), len(points)))
        _, labels = connected_components(graph, directed=False)
        for label in sorted(set(labels)):
            ids = np.flatnonzero(labels == label)
            if len(ids) < config.min_region_patches:
                continue
            selected = [significant[i] for i in ids]
            regions.append(
                GeometryRegion(
                    region_id=f"b31-region-{label}",
                    asset_id="BW-01",
                    association_status="associated",
                    bounds_world_m=(tuple(points[ids].min(0)), tuple(points[ids].max(0))),
                    representative_displacement_m=float(
                        np.median([p.displacement_m for p in selected])
                    ),
                    uncertainty_score_m=max(p.uncertainty_score_m for p in selected),
                    patch_ids=[p.patch_id for p in selected],
                    area_estimate_m2=len(ids) * config.patch_spacing_m**2,
                )
            )
    result = measured[0][1]
    sufficient = (
        len(choices) / max(len(patches), 1) >= config.min_valid_patch_fraction
        and registration.status == "valid"
    )
    result = result.model_copy(
        update={
            "analysis_id": "b31-" + registration.current_capture_id,
            "method": "multiscale_calibrated",
            "algorithm_version": "v3.1",
            "patches": patches,
            "regions": regions,
            "calibration_id": calibration["calibration_id"],
            "status": "valid" if sufficient else "insufficient_coverage",
            "significant": bool(regions) if sufficient else None,
            "asset_statuses": {
                a: ("valid" if a == "BW-01" and sufficient else "insufficient_coverage")
                for a in config.monitored_assets
            },
            "measurement_basis": "localized_relative",
            "reinspection_candidate": not sufficient,
            "processing_configuration_sha256": fingerprint(config),
            "quality_flags": []
            if sufficient
            else ["insufficient_qualified_patch_or_calibration_support"],
            "sensitivity_statement": f"Localized wall-relative change only; calibrated cluster multiplier {multiplier}; no significant change under achieved coverage/sensitivity does not establish health",
            "runtime_s": time.perf_counter() - started,
        }
    )
    return result
