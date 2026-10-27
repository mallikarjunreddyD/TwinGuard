"""Open3D registration and observable quality gates; no evaluator or plant access."""

import time
import numpy as np
from scipy.spatial import cKDTree
from twinguard.core.analytics_contracts import RegistrationResult
from twinguard.core.spatial import Transform
from .reference import mask_asset


def point_cloud(points, normal_radius=0.26):
    import open3d as o3d

    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    if len(points) > 3:
        cloud.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(radius=normal_radius, max_nn=50)
        )
    return cloud


def apply(points, matrix):
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def normal_information(points, normals):
    if len(points) < 6:
        return 0.0
    centered = points - points.mean(0)
    scale = max(float(np.linalg.norm(np.ptp(points, axis=0))), 0.1)
    jacobian = np.column_stack([normals, np.cross(centered / scale, normals)])
    values = np.linalg.eigvalsh(jacobian.T @ jacobian / len(points))
    return float(max(0, values[0]) / max(values[-1], 1e-12))


def register(baseline, current, config, reference, method="robust_point_to_plane"):
    import open3d as o3d

    start = time.perf_counter()
    b = baseline.processing_world_m
    c = current.processing_world_m
    flags = []
    uncertainty = config.uncertainty_floor_m
    repeatability = 0.0
    correction = np.eye(4)
    base_pose = np.asarray(baseline.record.sensor_pose.matrix)
    cur_pose = np.asarray(current.record.sensor_pose.matrix)
    if len(b) < config.min_correspondences or len(c) < config.min_correspondences:
        flags.append("too_few_points")
    selected_b, selected_c = b, c
    fallback = False
    if method == "robust_point_to_plane" and not flags:

        def select(points, stable):
            mask = np.zeros(len(points), bool)
            for asset in reference.assets:
                if stable and asset.stable:
                    mask |= mask_asset(points, asset, config.roi_margin_m)
                if not stable and asset.asset_id in config.monitored_assets:
                    mask |= mask_asset(points, asset, 0.07)
            return points[mask if stable else ~mask]

        anchors_b, anchors_c = select(b, True), select(c, True)
        if min(len(anchors_b), len(anchors_c)) >= config.stable_min_points:
            anchor_cloud = point_cloud(anchors_b, config.normal_radius_m)
            if (
                normal_information(anchors_b, np.asarray(anchor_cloud.normals))
                >= config.min_conditioning
            ):
                selected_b, selected_c = anchors_b, anchors_c
            else:
                fallback = True
        else:
            fallback = True
        if fallback:
            selected_b, selected_c = select(b, False), select(c, False)
            flags.append("stable_reference_fallback")
    too_few = min(len(selected_b), len(selected_c)) < config.min_correspondences
    fitness = 0.0
    rmse = None
    count = 0
    conditioning = 0.0
    converged = False
    if not too_few and method != "pose_only":
        target = point_cloud(selected_b, config.normal_radius_m)
        source = point_cloud(selected_c, config.normal_radius_m)
        if method == "point_to_point":
            estimation = o3d.pipelines.registration.TransformationEstimationPointToPoint()
            scales = [config.registration_scales_m[0], config.registration_scales_m[-1]]
        else:
            estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane(
                o3d.pipelines.registration.TukeyLoss(k=config.robust_scale_m)
            )
            scales = config.registration_scales_m
        for distance in scales:
            result = o3d.pipelines.registration.registration_icp(
                source,
                target,
                distance,
                correction,
                estimation,
                o3d.pipelines.registration.ICPConvergenceCriteria(
                    max_iteration=config.registration_iterations
                ),
            )
            correction = np.asarray(result.transformation)
        if method == "robust_point_to_plane":
            perturb = np.eye(4)
            perturb[:3, 3] = [0.004, -0.003, 0.003]
            alternative = o3d.pipelines.registration.registration_icp(
                source,
                target,
                scales[-1],
                perturb @ correction,
                estimation,
                o3d.pipelines.registration.ICPConvergenceCriteria(
                    max_iteration=config.registration_iterations
                ),
            )
            repeatability = float(
                np.linalg.norm(alternative.transformation[:3, 3] - correction[:3, 3])
            )
            # Selection is based only on observed fitness/RMSE, never true transform error.
            if (alternative.fitness, -alternative.inlier_rmse) > (
                result.fitness,
                -result.inlier_rmse,
            ):
                result = alternative
                correction = np.asarray(result.transformation)
        fitness = float(result.fitness)
        rmse = float(result.inlier_rmse)
        count = len(result.correspondence_set)
        converged = count >= config.min_correspondences and np.isfinite(correction).all()
        transformed = apply(selected_c, correction)
        distance, index = cKDTree(selected_b).query(transformed)
        valid = distance <= config.registration_scales_m[-1]
        normals = np.asarray(target.normals)
        if valid.sum() >= 6:
            matched = selected_b[index[valid]]
            normal = normals[index[valid]]
            conditioning = normal_information(matched, normal)
            residual = np.einsum("ij,ij->i", transformed[valid] - matched, normal)
            robust_sigma = 1.4826 * np.median(np.abs(residual - np.median(residual)))
            uncertainty = float(max(config.uncertainty_floor_m, robust_sigma, repeatability))
    elif not too_few:
        distances, index = cKDTree(b).query(c)
        valid = distances <= config.registration_scales_m[-1]
        count = int(valid.sum())
        fitness = float(valid.mean())
        rmse = float(np.sqrt(np.mean(distances[valid] ** 2))) if count else None
        conditioning = normal_information(
            b, np.asarray(point_cloud(b, config.normal_radius_m).normals)
        )
        converged = True
    hard = []
    if too_few:
        hard.append("too_few_correspondences")
    if count < config.min_correspondences:
        hard.append("too_few_correspondences")
    if fitness < config.min_fitness:
        hard.append("insufficient_overlap")
    if conditioning < config.min_conditioning:
        hard.append("weakly_constrained_geometry")
    if rmse is None or rmse > config.max_inlier_rmse_m:
        hard.append("excessive_residual")
    if repeatability > config.max_repeatability_m:
        hard.append("unstable_initialization")
    translation = np.linalg.norm(correction[:3, 3])
    angle = np.arccos(np.clip((np.trace(correction[:3, :3]) - 1) / 2, -1, 1))
    expected_translation = max(
        0.05,
        6
        * (
            (baseline.record.reported_translation_std_m or 0)
            + (current.record.reported_translation_std_m or 0)
            + 3
            * (
                (baseline.record.reported_rotation_std_rad or 0)
                + (current.record.reported_rotation_std_rad or 0)
            )
        ),
    )
    expected_rotation = max(
        0.02,
        6
        * (
            (baseline.record.reported_rotation_std_rad or 0)
            + (current.record.reported_rotation_std_rad or 0)
        ),
    )
    if translation > min(config.max_translation_correction_m, expected_translation) or angle > min(
        config.max_rotation_correction_rad, expected_rotation
    ):
        hard.append("correction_exceeds_pose_budget")
    transform = np.linalg.inv(base_pose) @ correction @ cur_pose
    rigid = Transform(
        source=current.record.sensor_pose.source,
        target=baseline.record.sensor_pose.source,
        matrix=transform.tolist(),
    )
    output = RegistrationResult(
        registration_id="reg-" + method + "-" + current.record.capture_id,
        baseline_capture_id=baseline.record.capture_id,
        current_capture_id=current.record.capture_id,
        transform=rigid,
        method=method,
        status="inconclusive" if hard else "valid",
        converged=converged and not hard,
        fitness=fitness,
        inlier_rmse_m=rmse,
        correspondence_count=count,
        conditioning_ratio=conditioning,
        uncertainty_score_m=uncertainty,
        repeatability_m=repeatability,
        quality_flags=sorted(set(flags + hard)),
        runtime_s=time.perf_counter() - start,
    )
    registered_world = apply(current.processing_sensor_m, base_pose @ transform)
    return output, registered_world
