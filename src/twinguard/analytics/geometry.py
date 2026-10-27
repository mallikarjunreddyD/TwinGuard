"""Normal-projected patch screening with conservative, non-probabilistic scores."""

import time
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from twinguard.core.analytics_contracts import GeometryResult, PatchEstimate, GeometryRegion
from twinguard.core.contracts import GeometricDetection
from .reference import mask_asset, associate


def basis(normal):
    helper = np.array([1.0, 0, 0]) if abs(normal[0]) < 0.8 else np.array([0.0, 0, 1])
    a = np.cross(normal, helper)
    a /= np.linalg.norm(a)
    return a, np.cross(normal, a)


def cells(points, center, normal, radius):
    a, b = basis(normal)
    xy = np.column_stack([(points - center) @ a, (points - center) @ b])
    indices = np.floor((xy / radius + 1) * 2).astype(int)
    return {tuple(row) for row in indices if np.all((row >= 0) & (row < 4))}


def robust_scale(values):
    return float(1.4826 * np.median(np.abs(values - np.median(values)))) if len(values) else 0.0


def patch_centers(points, asset, config):
    if asset.plane_point_world_m is not None:
        lo, hi = np.asarray(asset.bounds_world_m)
        x = np.arange(lo[0] + config.patch_spacing_m / 2, hi[0], config.patch_spacing_m)
        z = np.arange(lo[2] + config.patch_spacing_m / 2, hi[2], config.patch_spacing_m)
        return np.array([[i, asset.plane_point_world_m[1], j] for i in x for j in z])
    if not len(points):
        return np.empty((0, 3))
    voxel = np.floor(points / config.patch_spacing_m).astype(int)
    _, indices = np.unique(voxel, axis=0, return_index=True)
    return points[indices]


def detect_geometry(
    baseline,
    current_world,
    registration,
    reference,
    config,
    calibration=None,
    method="patch_screening",
):
    start = time.perf_counter()
    b = baseline.processing_world_m
    c = np.asarray(current_world)
    patches = []
    calibration = calibration or {
        "calibration_id": "uncalibrated-prior",
        "uncertainty_floor_m": config.uncertainty_floor_m,
        "threshold_m": config.change_threshold_m,
    }
    threshold = max(config.change_threshold_m, calibration["threshold_m"])
    for asset in reference.assets:
        if asset.asset_id not in config.monitored_assets:
            continue
        bp = b[mask_asset(b, asset, 0.05)]
        cp = c[mask_asset(c, asset, config.max_projection_m + 0.05)]
        centers = patch_centers(bp, asset, config)
        btree = cKDTree(bp) if len(bp) else None
        ctree = cKDTree(cp) if len(cp) else None
        for i, center in enumerate(centers):
            prior = np.asarray(asset.normal_world or [0, 1, 0], float)
            record = dict(
                patch_id=f"{asset.asset_id}-patch-{i}",
                asset_id=asset.asset_id,
                center_world_m=tuple(center),
                normal_world=tuple(prior),
                direction="unreliable",
                baseline_points=0,
                current_points=0,
                common_coverage=0.0,
                displacement_m=None,
                uncertainty_score_m=None,
                engineering_margin_m=None,
                threshold_m=threshold,
                significant=None,
                status="insufficient_coverage",
                quality_flags=[],
            )
            if registration.status != "valid":
                record["quality_flags"] = ["registration_unreliable"]
                patches.append(PatchEstimate(**record))
                continue
            bi = btree.query_ball_point(center, config.normal_radius_m) if btree else []
            near = bp[bi]
            if len(near) < config.min_patch_points:
                patches.append(PatchEstimate(**record))
                continue
            covariance = np.cov((near - near.mean(0)).T)
            eigenvalues, eigenvectors = np.linalg.eigh(covariance)
            normal = eigenvectors[:, 0]
            direction = "oriented"
            if asset.normal_world is not None:
                if abs(normal @ prior) < 0.7:
                    direction = "unsigned"
                if normal @ prior < 0:
                    normal = -normal
            else:
                view = np.asarray(baseline.record.sensor_pose.matrix)[:3, 3] - center
                if abs(normal @ view) / max(np.linalg.norm(view), 1e-10) < 0.2:
                    direction = "unsigned"
                if normal @ view < 0:
                    normal = -normal
            record.update(normal_world=tuple(normal), direction=direction)
            if eigenvalues[1] / max(eigenvalues[2], 1e-12) < 0.01:
                record.update(status="inconclusive", quality_flags=["neighborhood_is_line_like"])
                patches.append(PatchEstimate(**record))
                continue

            # Fixed normal slab avoids opposite/adjacent surfaces, without semantic hit labels.
            def neighborhood(points, tree):
                ids = (
                    tree.query_ball_point(center, config.patch_radius_m + config.max_projection_m)
                    if tree
                    else []
                )
                p = points[ids]
                if not len(p):
                    return p
                offset = p - center
                project = offset @ normal
                tangent = np.linalg.norm(offset - project[:, None] * normal, axis=1)
                return p[
                    (tangent <= config.patch_radius_m)
                    & (np.abs(project) <= config.max_projection_m)
                ]

            left = neighborhood(bp, btree)
            right = neighborhood(cp, ctree)
            record.update(baseline_points=len(left), current_points=len(right))
            if min(len(left), len(right)) < config.min_patch_points:
                patches.append(PatchEstimate(**record))
                continue
            a = (left - center) @ normal
            d = (right - center) @ normal
            # Reject separated depth populations instead of averaging opposite tube walls.
            if any(
                np.max(np.diff(np.sort(values))) > config.max_roughness_m * 3 for values in (a, d)
            ):
                record.update(status="invalid", quality_flags=["multiple_depth_layers"])
                patches.append(PatchEstimate(**record))
                continue
            spread = max(robust_scale(a), robust_scale(d))
            if spread > config.max_roughness_m:
                record.update(status="inconclusive", quality_flags=["excessive_local_roughness"])
                patches.append(PatchEstimate(**record))
                continue
            cells_a = cells(left, center, normal, config.patch_radius_m)
            cells_b = cells(right, center, normal, config.patch_radius_m)
            common = cells_a & cells_b
            coverage = len(common) / max(len(cells_a | cells_b), 1)
            record["common_coverage"] = coverage
            if len(common) < config.min_common_cells or coverage < config.min_common_coverage:
                patches.append(PatchEstimate(**record))
                continue
            if method == "nearest_neighbor":
                distance, _ = cKDTree(left).query(right)
                estimate = float(np.median(distance))
                uncertainty = 0.0
                decision_threshold = config.nearest_threshold_m
            else:
                estimate = float(np.median(d) - np.median(a))
                # No sqrt(N): neighboring beams/patches are correlated. Use the largest
                # overlapping variability contribution, not duplicated variance sums.
                uncertainty = float(
                    max(
                        spread, calibration["uncertainty_floor_m"], registration.uncertainty_score_m
                    )
                )
                decision_threshold = threshold
            if direction != "oriented":
                estimate = abs(estimate)
            margin = (
                abs(estimate) - config.uncertainty_multiplier * uncertainty - decision_threshold
            )
            record.update(
                displacement_m=estimate,
                uncertainty_score_m=uncertainty,
                engineering_margin_m=margin,
                threshold_m=decision_threshold,
                significant=bool(margin > 0),
                status="valid",
            )
            patches.append(PatchEstimate(**record))
    significant = [p for p in patches if p.significant]
    regions = []
    if significant:
        points = np.asarray([p.center_world_m for p in significant])
        pairs = cKDTree(points).query_pairs(config.patch_spacing_m * 1.8)
        rows = []
        cols = []
        for i, j in pairs:
            rows.extend([i, j])
            cols.extend([j, i])
        graph = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(points), len(points)))
        _, labels = connected_components(graph, directed=False)
        for label in sorted(set(labels)):
            indices = np.flatnonzero(labels == label)
            if len(indices) < config.min_region_patches:
                continue
            group = [significant[i] for i in indices]
            center = points[indices].mean(0)
            asset_id = associate(center, reference, 0.03)
            displacement = float(np.median([p.displacement_m for p in group]))
            uncertainty = float(max(p.uncertainty_score_m for p in group))
            low = points[indices].min(0)
            high = points[indices].max(0)
            legacy = None
            if asset_id:
                legacy = GeometricDetection(
                    detection_id=f"detection-{registration.current_capture_id}-{label}",
                    asset_id=asset_id,
                    baseline_capture_id=registration.baseline_capture_id,
                    current_capture_id=registration.current_capture_id,
                    region_id=f"region-{label}",
                    displacement_m=displacement,
                    displacement_uncertainty_m=uncertainty,
                    quality_status="partial",
                    algorithm_id=method,
                    algorithm_version="v1",
                    detected_at=baseline.record.acquired_at,
                )
            regions.append(
                GeometryRegion(
                    region_id=f"region-{label}",
                    asset_id=asset_id,
                    association_status="associated" if asset_id else "ambiguous",
                    bounds_world_m=(tuple(low), tuple(high)),
                    representative_displacement_m=displacement,
                    uncertainty_score_m=uncertainty,
                    patch_ids=[p.patch_id for p in group],
                    area_estimate_m2=len(group) * config.patch_spacing_m**2,
                    legacy_detection=legacy,
                )
            )
    asset_statuses = {}
    for asset_id in config.monitored_assets:
        group = [p for p in patches if p.asset_id == asset_id]
        fraction = sum(p.status == "valid" for p in group) / max(len(group), 1)
        asset_statuses[asset_id] = (
            "valid"
            if group
            and fraction >= config.min_valid_patch_fraction
            and registration.status == "valid"
            else "insufficient_coverage"
        )
    valid = sum(p.status == "valid" for p in patches)
    sufficient = (
        registration.status == "valid"
        and valid / max(len(patches), 1) >= config.min_valid_patch_fraction
    )
    status = "valid" if sufficient else "insufficient_coverage"
    return GeometryResult(
        analysis_id="geometry-" + method + "-" + registration.current_capture_id,
        baseline_capture_id=registration.baseline_capture_id,
        current_capture_id=registration.current_capture_id,
        acquired_at=baseline.record.acquired_at,
        method=method,
        registration_id=registration.registration_id,
        reference_id=reference.reference_id,
        calibration_id=calibration["calibration_id"],
        status=status,
        asset_statuses=asset_statuses,
        patches=patches,
        regions=regions,
        significant=bool(regions) if sufficient else None,
        sensitivity_statement="Engineering screening using correlated local variability and registration score; not a calibrated 95% confidence interval",
        runtime_s=time.perf_counter() - start,
    )
