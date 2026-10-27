"""Numerical radiometric residuals with conservative saturation/viewpoint gates."""

from pathlib import Path
import json
import hashlib
import numpy as np
from scipy.ndimage import median_filter, label
from twinguard.core.contracts import InspectionCapture
from twinguard.core.analytics_contracts import ThermalResult, ThermalRegion
from twinguard.core.observations import load_public_observations, load_capture_arrays
from .operating import causal_load, measured_records


def quantitative_mask(arrays, record):
    available = arrays["valid_mask"] & np.isfinite(arrays["temperature_c"])
    saturated = arrays.get("saturation_mask")
    if saturated is None:
        return np.zeros_like(available), np.zeros_like(available), False
    valid = available & ~saturated
    params = record.acquisition_parameters
    if "measurement_min_c" in params:
        valid &= arrays["temperature_c"] >= params["measurement_min_c"]
    if "measurement_max_c" in params:
        valid &= arrays["temperature_c"] <= params["measurement_max_c"]
    return valid, saturated, True


def thermal_feature(record, records, model, config):
    temperature = next(
        (m for m in model["sensors"].values() if m["measurement_type"] == "temperature"), None
    )
    tau = temperature["tau_s"] if temperature else 25
    loads = [r for r in records if r.measurement_type == "operating_load"]
    return causal_load(record, loads, tau, config.load_age_limit_s)


def calibrate_thermal(datasets, operating, config, output: Path):
    frames = []
    masks = []
    loads = []
    ids = []
    pose = None
    shape = None
    for directory in datasets:
        records = load_public_observations(Path(directory))
        iot = measured_records(directory)
        for record in records:
            if not isinstance(record, InspectionCapture) or record.modality != "thermal":
                continue
            arrays = load_capture_arrays(Path(directory), record)
            valid, _, known = quantitative_mask(arrays, record)
            if not known:
                continue
            feature = thermal_feature(record, iot, operating, config)
            if feature is None:
                continue
            if shape is None:
                shape = valid.shape
                pose = record.sensor_pose.matrix
            if valid.shape != shape:
                raise ValueError("Thermal training shapes differ")
            frames.append(arrays["temperature_c"])
            masks.append(valid)
            loads.append(feature)
            ids.append(record.provenance_id)
    if len(frames) < config.thermal_min_training_frames:
        raise ValueError("Insufficient quantitative healthy thermal frames")
    values = np.asarray(frames)
    mask = np.asarray(masks)
    x = np.asarray(loads)
    weight = mask.astype(float)
    y = np.nan_to_num(values)
    n = weight.sum(0)
    sx = (weight * x[:, None, None]).sum(0)
    sxx = (weight * x[:, None, None] ** 2).sum(0)
    sy = (y * weight).sum(0)
    sxy = (y * weight * x[:, None, None]).sum(0)
    denominator = n * sxx - sx * sx
    slope = np.divide(
        n * sxy - sx * sy, denominator, out=np.zeros_like(n), where=np.abs(denominator) > 1e-8
    )
    intercept = np.divide(sy - slope * sx, n, out=np.zeros_like(n), where=n > 0)
    prediction = intercept[None] + slope[None] * x[:, None, None]
    residual = np.where(mask, values - prediction, np.nan)
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        variability = 1.4826 * np.nanmedian(
            np.abs(residual - np.nanmedian(residual, axis=0)), axis=0
        )
        steady = np.abs(x - 0.5) < 0.025
        static = (
            np.nanmedian(np.where(mask[steady], values[steady], np.nan), axis=0)
            if steady.any()
            else intercept + slope * 0.5
        )
    calibrated = (
        (n >= config.thermal_min_training_frames) & np.isfinite(variability) & np.isfinite(static)
    )
    variability = np.maximum(np.nan_to_num(variability, nan=1e6), 0.5)
    identity = hashlib.sha256(
        np.nan_to_num(intercept).tobytes() + np.nan_to_num(slope).tobytes()
    ).hexdigest()[:16]
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output / "thermal_model.npz",
        intercept=intercept,
        slope=slope,
        static=static,
        scale=variability,
        calibrated=calibrated,
    )
    model = {
        "schema_version": "1.0.0",
        "model_id": "thermal-" + identity,
        "training_datasets": sorted(set(ids)),
        "training_frames": len(frames),
        "load_range": [float(min(x)) - 0.01, float(max(x)) + 0.01],
        "reported_reference_pose": pose,
        "shape": list(shape) if shape is not None else [],
        "array_uri": "thermal_model.npz",
        "operating_model": operating,
        "domain": "apparent radiometric temperature, not hidden physical temperature",
    }
    (output / "thermal_model.json").write_text(json.dumps(model, indent=2) + "\n")
    return model


def infer_thermal(root, record, model_dir, config, reference=None, method="conditioned"):
    model = json.loads((Path(model_dir) / "thermal_model.json").read_text())
    with np.load(Path(model_dir) / model["array_uri"], allow_pickle=False) as archive:
        parameters = {k: archive[k] for k in archive.files}
    arrays = load_capture_arrays(Path(root), record)
    valid, saturated, known = quantitative_mask(arrays, record)
    flags = []
    status = "valid"
    regions = []
    residual = np.full(valid.shape, np.nan)
    candidates = np.zeros(valid.shape, bool)
    if not known:
        status = "inconclusive"
        flags.append("legacy_saturation_unknown")
    elif list(valid.shape) != model["shape"]:
        status = "invalid"
        flags.append("camera_shape_mismatch")
    else:
        pose = np.asarray(record.sensor_pose.matrix)
        anchor = np.asarray(model["reported_reference_pose"])
        angle = np.arccos(np.clip((np.trace(pose[:3, :3] @ anchor[:3, :3].T) - 1) / 2, -1, 1))
        if (
            np.linalg.norm(pose[:3, 3] - anchor[:3, 3]) > config.thermal_max_pose_delta_m
            or angle > config.thermal_max_rotation_delta_rad
        ):
            status = "inconclusive"
            flags.append("viewpoint_outside_template_support")
        feature = thermal_feature(record, measured_records(root), model["operating_model"], config)
        if feature is None:
            status = "inconclusive"
            flags.append("missing_operating_context")
        elif not model["load_range"][0] <= feature <= model["load_range"][1]:
            status = "out_of_reference_range"
            flags.append("uncalibrated_load")
        valid &= parameters["calibrated"]
        if valid.mean() < config.thermal_min_valid_fraction:
            status = "insufficient_coverage"
            flags.append("insufficient_quantitative_pixels")
        if status == "valid":
            expected = (
                parameters["static"]
                if method == "static"
                else parameters["intercept"] + parameters["slope"] * feature
            )
            residual[valid] = arrays["temperature_c"][valid] - expected[valid]
            filtered = median_filter(np.nan_to_num(residual), size=3)
            candidates = valid & (filtered > config.thermal_threshold_c + 2 * parameters["scale"])
            labels, count = label(candidates)
            for index in range(1, count + 1):
                pixels = np.argwhere(labels == index)
                if len(pixels) < config.thermal_min_pixels:
                    continue
                y0, x0 = pixels.min(0)
                y1, x1 = pixels.max(0) + 1
                regions.append(
                    ThermalRegion(
                        region_id=f"thermal-region-{index}",
                        image_bounds=(int(x0), int(y0), int(x1), int(y1)),
                        pixel_count=len(pixels),
                        asset_id=None,
                        association_status="image_only",
                        peak_residual_c=float(np.max(residual[labels == index])),
                        median_residual_c=float(np.median(residual[labels == index])),
                        uncertainty_score_c=float(np.max(parameters["scale"][labels == index])),
                    )
                )
    result = ThermalResult(
        analysis_id="thermal-" + method + "-" + record.capture_id,
        capture_id=record.capture_id,
        acquired_at=record.acquired_at,
        model_id=model["model_id"],
        method=method,
        status=status,
        valid_pixels=int(valid.sum()),
        saturated_pixels=int(saturated.sum()),
        total_pixels=valid.size,
        saturation_known=known,
        regions=regions,
        significant=bool(regions) if status == "valid" else None,
        quality_flags=flags,
    )
    return result, {
        "residual_c": residual,
        "quantitative_mask": valid,
        "saturation_mask": saturated,
        "candidate_mask": candidates,
    }
