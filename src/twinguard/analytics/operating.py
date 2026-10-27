"""Frozen healthy-data models and causal load conditioning; no simulator imports."""

from pathlib import Path
import json
import hashlib
import numpy as np
from twinguard.core.contracts import SensorObservation
from twinguard.core.observations import load_public_observations
from twinguard.core.analytics_contracts import OperatingPrediction


def measured_records(root):
    return [r for r in load_public_observations(Path(root)) if isinstance(r, SensorObservation)]


def causal_load(record, loads, tau, max_age):
    eligible = sorted(
        (
            r
            for r in loads
            if r.acquired_at <= record.acquired_at
            and r.received_at <= record.received_at
            and r.quality == "good"
        ),
        key=lambda r: r.acquired_at,
    )
    if not eligible:
        return None
    # Retransmissions do not create additional independent measurements.
    eligible = list({r.observation_id: r for r in eligible}.values())
    if (record.acquired_at - eligible[-1].acquired_at).total_seconds() > max_age:
        return None
    if tau == 0:
        return float(eligible[-1].value)
    state = float(eligible[0].value)
    last = eligible[0].acquired_at
    value = state
    for sample in eligible[1:]:
        dt = (sample.acquired_at - last).total_seconds()
        state = value + (state - value) * np.exp(-dt / tau)
        last = sample.acquired_at
        value = float(sample.value)
    dt = (record.acquired_at - last).total_seconds()
    return float(value + (state - value) * np.exp(-dt / tau))


def robust_fit(x, y):
    coefficient = np.linalg.lstsq(x, y, rcond=None)[0]
    for _ in range(8):
        residual = y - x @ coefficient
        scale = max(1.4826 * np.median(np.abs(residual - np.median(residual))), 1e-8)
        weights = np.minimum(1, 1.5 * scale / np.maximum(np.abs(residual), 1e-8))
        coefficient = np.linalg.lstsq(
            x * np.sqrt(weights[:, None]), y * np.sqrt(weights), rcond=None
        )[0]
    return coefficient


def calibrate_operating(datasets, config):
    collections = []
    for path in datasets:
        records = measured_records(path)
        manifest = json.loads((Path(path) / "manifest.json").read_text())
        collections.append((manifest["dataset"]["dataset_id"], records))
    sensors = sorted(
        {
            r.sensor_id
            for _, rows in collections
            for r in rows
            if r.measurement_type != "operating_load"
        }
    )
    models = {}
    for sensor_id in sensors:
        target = next(r for _, rows in collections for r in rows if r.sensor_id == sensor_id)
        minimum = (
            config.operating_min_scale_pressure
            if target.measurement_type == "pressure"
            else config.operating_min_scale_temperature
            if target.measurement_type == "temperature"
            else 0.01
        )
        choices = []
        for tau in config.lag_candidates_s:
            x = []
            y = []
            groups = []
            static_values = []
            for group, (_, records) in enumerate(collections):
                loads = [r for r in records if r.measurement_type == "operating_load"]
                for r in records:
                    if (
                        r.sensor_id != sensor_id
                        or r.quality != "good"
                        or r.delivery_status == "duplicate"
                    ):
                        continue
                    feature = causal_load(r, loads, tau, config.load_age_limit_s)
                    if feature is None:
                        continue
                    x.append([1, feature])
                    y.append(float(r.value))
                    groups.append(group)
                    recent = [
                        float(s.value)
                        for s in loads
                        if s.acquired_at <= r.acquired_at
                        and s.received_at <= r.received_at
                        and (r.acquired_at - s.acquired_at).total_seconds() <= 10
                    ]
                    if recent and max(recent) - min(recent) < 0.02 and abs(feature - 0.5) < 0.025:
                        static_values.append(float(r.value))
            if len(y) < 8:
                continue
            x = np.asarray(x)
            y = np.asarray(y)
            groups = np.asarray(groups)
            train = groups % 3 != 2
            valid = ~train
            if train.sum() < 5 or valid.sum() < 3:
                train = np.ones(len(y), bool)
                valid = train
            coefficient = robust_fit(x[train], y[train])
            residual = y[valid] - x[valid] @ coefficient
            score = float(np.median(np.abs(residual)))
            choices.append((score, tau, x, y, static_values))
        if not choices:
            continue
        _, tau, x, y, static_values = min(choices, key=lambda row: (row[0], row[1]))
        coefficient = robust_fit(x, y)
        residual = y - x @ coefficient
        scale = float(max(minimum, 1.4826 * np.median(np.abs(residual - np.median(residual)))))
        static = np.asarray(static_values or y.tolist())
        median = float(np.median(static))
        static_scale = float(max(minimum, 1.4826 * np.median(np.abs(static - median))))
        models[sensor_id] = {
            "coefficients": coefficient.tolist(),
            "tau_s": tau,
            "residual_scale": scale,
            "static_reference": median,
            "static_scale": static_scale,
            "load_range": [float(x[:, 1].min()) - 0.01, float(x[:, 1].max()) + 0.01],
            "training_samples": len(y),
            "unit": target.unit,
            "asset_id": target.asset_id,
            "measurement_type": target.measurement_type,
        }
    if not models:
        raise ValueError("No usable healthy calibration records")
    identity = hashlib.sha256(json.dumps(models, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "schema_version": "1.0.0",
        "model_id": "operating-" + identity,
        "version": "v1",
        "training_datasets": [name for name, _ in collections],
        "feature_definition": "causal zero-order-hold exponential filter of received measured load; intercept plus filtered load",
        "validation_selection": "healthy dataset groups modulo 3 held out for lag selection, then robust refit; no evaluation faults",
        "configuration": config.model_dump(mode="json"),
        "sensors": models,
    }


def infer_operating(records, model, config, method="conditioned_quality"):
    records = sorted(records, key=lambda r: (r.received_at, r.sensor_id, r.observation_id))
    loads = [r for r in records if r.measurement_type == "operating_load"]
    predictions = []
    seen = set()
    for record in records:
        if record.measurement_type == "operating_load" or record.observation_id in seen:
            continue
        seen.add(record.observation_id)
        m = model["sensors"].get(record.sensor_id)
        status = "valid"
        flags = []
        expected = None
        residual = None
        significant = None
        scale = None
        threshold = None
        if m is None:
            status = "inconclusive"
            flags.append("sensor_not_calibrated")
        elif record.quality == "invalid":
            status = "invalid"
            flags.append("invalid_sensor_quality")
        elif method == "conditioned_quality" and (
            record.quality != "good"
            or (record.received_at - record.acquired_at).total_seconds() > config.max_delay_s
        ):
            status = "inconclusive"
            flags.append("measurement_quality_or_delay")
        else:
            if method == "static":
                expected = m["static_reference"]
                scale = m["static_scale"]
            else:
                load = causal_load(record, loads, m["tau_s"], config.load_age_limit_s)
                if load is None:
                    status = "inconclusive"
                    flags.append("missing_current_load")
                elif not m["load_range"][0] <= load <= m["load_range"][1]:
                    status = "out_of_reference_range"
                    flags.append("uncalibrated_load")
                else:
                    expected = m["coefficients"][0] + m["coefficients"][1] * load
                    scale = m["residual_scale"]
            if expected is not None:
                residual = float(record.value) - expected
                threshold = config.operating_k * scale
                significant = bool(abs(residual) > threshold)
        predictions.append(
            OperatingPrediction(
                prediction_id=method + "-" + record.observation_id,
                observation_id=record.observation_id,
                sensor_id=record.sensor_id,
                asset_id=record.asset_id,
                acquired_at=record.acquired_at,
                available_at=record.received_at,
                model_id=model["model_id"],
                method=method,
                observed_value=float(record.value),
                estimated_reference=expected,
                residual=residual,
                uncertainty_score=scale,
                threshold=threshold,
                unit=record.unit,
                significant=significant,
                status=status,
                quality_flags=flags,
            )
        )
    return predictions
