"""Deterministic accepted-geometry shells and modality-specific suitability."""

from pathlib import Path
import numpy as np
from .contracts import CandidateViewpoint
from .observations import fingerprint
from .visibility import look_at, predict
from .feasibility import evaluate


def generate(surface, snapshot, config, root=Path(".")):
    sensor_file = root / config.sensor_path
    import yaml

    installation = yaml.safe_load(sensor_file.read_text())
    result = []
    for state in sorted(snapshot.assets, key=lambda a: a.asset_id):
        points = surface.centers[surface.assets == state.asset_id]
        if not len(points):
            raise ValueError("Asset absent from accepted map: " + state.asset_id)
        center = (points.min(axis=0) + points.max(axis=0)) / 2
        for modality in config.available_modalities:
            sensor = installation[modality]
            for radius in config.stand_off_shells_m:
                for az in config.azimuths_rad:
                    for dz in config.elevation_offsets_m:
                        position = center + np.array([radius * np.sin(az), radius * np.cos(az), dz])
                        pose = look_at(position, center, sensor["sensor_id"])
                        visible, usable, distance, incidence, spacing, support = predict(
                            surface, pose, sensor, modality, state.asset_id, config
                        )
                        reasons = []
                        if not visible:
                            reasons.append("no_in_range_visible_surface")
                        if not usable:
                            reasons.append("insufficient_incidence_or_coverage")
                        if not sensor.get("calibration_reference"):
                            reasons.append("missing_calibration_reference")
                        if installation["fidelity"] not in config.calibrated_fidelities:
                            reasons.append("unsupported_sensor_precision_L2")
                        if (
                            not config.calibrated_range_m[0]
                            <= distance
                            <= config.calibrated_range_m[1]
                        ):
                            reasons.append("outside_calibrated_range")
                        if modality == "lidar":
                            if state.asset_id not in config.calibrated_assets:
                                reasons.append("no_B31_asset_calibration")
                            if support < config.minimum_registration_returns:
                                reasons.append("insufficient_registration_support")
                            if spacing > config.maximum_vertical_spacing_m:
                                reasons.append("insufficient_patch_sampling")
                        else:
                            if not state.thermal_image_only:
                                reasons.append(
                                    "thermal_context_not_requested_for_geometric_deficiency"
                                )
                            original = np.asarray(sensor["pose"]["matrix"])
                            rotation = np.asarray(pose.matrix)[:3, :3]
                            angle = np.arccos(
                                np.clip((np.trace(original[:3, :3].T @ rotation) - 1) / 2, -1, 1)
                            )
                            if np.linalg.norm(original[:3, 3] - position) > 0.15 or angle > 0.08:
                                reasons.append(
                                    "thermal_reference_pose_outside_existing_model_support"
                                )
                        quality = float(
                            np.clip(
                                incidence
                                * (1 - min(1, spacing / config.maximum_vertical_spacing_m)),
                                0,
                                1,
                            )
                        )
                        ident = (
                            "view-"
                            + fingerprint(
                                [
                                    surface.hash,
                                    state.asset_id,
                                    modality,
                                    pose.model_dump(mode="json"),
                                    fingerprint(installation),
                                ]
                            )[:24]
                        )
                        result.append(
                            CandidateViewpoint(
                                viewpoint_id=ident,
                                asset_id=state.asset_id,
                                intended_region="accepted reference surface; no inferred fault location",
                                modality=modality,
                                planned_pose=pose,
                                sensor_reference=str(sensor_file),
                                calibration_reference=sensor.get("calibration_reference"),
                                expected_range_m=distance,
                                incidence_cosine_mean=incidence,
                                predicted_visible_cells=visible,
                                predicted_usable_cells=usable if not reasons else [],
                                expected_usable_area_m2=surface.area_of(usable)
                                if not reasons
                                else 0,
                                predicted_spacing_m=spacing,
                                expected_quality=quality if not reasons else 0,
                                registration_support_returns=support,
                                acquisition_s=config.acquisition_s,
                                feasibility=evaluate(
                                    surface, position, state.asset_id, config, reasons
                                ),
                                assumptions=[
                                    "Planned sensor pose, not an actual UAV pose",
                                    "Expected reference coverage, not measured evidence",
                                    "Registration return count is a preinspection proxy, not a conditioning guarantee",
                                    "Unknown current obstructions and dynamic hazards remain",
                                    "B3.1 localized_relative only; physical calibration unvalidated",
                                ],
                            )
                        )
    return sorted(result, key=lambda c: (c.asset_id, c.modality, c.viewpoint_id))
