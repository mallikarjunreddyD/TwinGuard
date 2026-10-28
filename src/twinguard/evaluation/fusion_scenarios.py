"""Restricted controlled E3-A fixtures and expected policy properties, never engine inputs."""

from datetime import datetime, timezone, timedelta
import random
from twinguard.fusion.models import FusionEvidence, OperatorAction, MonitoringRequirement

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def evidence(
    identifier, kind="pressure", finding="negative", t=0, delay=0.2, asset="BW-01", **updates
):
    modality = (
        "geometric" if kind == "geometry" else "thermal" if kind == "thermal" else "fixed_sensor"
    )
    hypothesis = {
        "pressure": "critical_pressure_limit",
        "temperature": "critical_temperature_limit",
        "residual": "abnormal_process_pressure_residual",
        "geometry": "localized_geometric_change",
        "thermal": "abnormal_thermal_residual",
    }[kind]
    sensor = {
        "pressure": "pressure-01",
        "temperature": "temperature-01",
        "residual": "pressure-01",
    }.get(kind)
    value = (
        1300000
        if kind == "pressure" and finding == "positive"
        else 1000000
        if kind == "pressure"
        else 260
        if kind == "temperature" and finding == "positive"
        else 150
        if kind == "temperature"
        else 0.01
        if kind == "geometry"
        else 10
        if kind == "thermal"
        else 100000
    )
    qualified = finding in ["positive", "negative"]
    raw = dict(
        evidence_id=identifier,
        source_id=identifier,
        modality=modality,
        algorithm="engineering_limit"
        if kind in ["pressure", "temperature"]
        else "multiscale_calibrated"
        if kind == "geometry"
        else "conditioned_quality",
        algorithm_version="v1",
        provenance_id="controlled-public-fixture",
        asset_id=asset,
        sensor_id=sensor,
        acquired_at=START + timedelta(seconds=t),
        received_at=START + timedelta(seconds=t + delay / 2),
        processed_at=START + timedelta(seconds=t + delay),
        available_at=START + timedelta(seconds=t + delay),
        availability_basis="simulated_replay",
        clock_quality="synchronized",
        hypothesis=hypothesis,
        finding=finding,
        value=value if qualified else None,
        observed_value=value if kind in ["pressure", "temperature"] and qualified else None,
        unit="Pa" if kind in ["pressure", "residual"] else "m" if kind == "geometry" else "degC",
        scope="engineering_limit"
        if kind in ["pressure", "temperature"]
        else "localized_wall"
        if kind == "geometry"
        else "apparent_image_temperature"
        if kind == "thermal"
        else "operating_reference",
        measurement_basis="configured_instrument_reading"
        if kind in ["pressure", "temperature"]
        else "localized_relative"
        if kind == "geometry"
        else "calibrated_operating_residual",
        qualification_status="valid" if qualified else "inconclusive",
        association="associated" if asset else "image_only",
        origin_identity=identifier,
        dependence_group="sensor-" + sensor if sensor else identifier,
        quality="good" if qualified else "unknown",
        calibration_valid=qualified,
        registration_valid=qualified if kind == "geometry" else None,
        coverage_status="valid" if qualified else "insufficient_coverage",
        authoritative_limit=qualified and kind in ["pressure", "temperature"],
    )
    raw.update(updates)
    return FusionEvidence.model_validate(raw)


def controlled(case, seed, base_policy):
    policy = base_policy.model_copy(deep=True)
    prefix = f"c{case:02d}-s{seed}-"
    e = []
    actions = []
    at = START + timedelta(seconds=5)
    target = "BW-01"
    expected = "green"
    normal = [
        evidence(prefix + "pressure"),
        evidence(prefix + "temperature", "temperature"),
        evidence(prefix + "reference", "residual"),
        evidence(prefix + "geometry", "geometry"),
    ]

    def without(kind):
        return [x for x in normal if x.hypothesis != kind]

    e = list(normal)
    if case == 2:
        e = without("localized_geometric_change") + [
            evidence(prefix + "geo-positive", "geometry", "positive", 1)
        ]
        expected = "amber"
    if case == 3:
        e.append(evidence(prefix + "thermal", "thermal", "positive", 1, asset=None))
        target = "inspection-context"
        expected = "amber"
    if case == 4:
        e = without("abnormal_process_pressure_residual") + [
            evidence(prefix + "residual", "residual", "positive", 1)
        ]
        expected = "amber"
    if case in [5, 6, 7, 13, 17, 18, 19, 20]:
        e = without("critical_pressure_limit") + [
            evidence(prefix + "critical", "pressure", "positive", 1)
        ]
        expected = "red"
    if case == 6:
        e = [x for x in e if x.modality != "geometric"]
    if case == 7:
        e.append(evidence(prefix + "old-thermal", "thermal", "positive", -500, asset="BW-01"))
    if case == 8:
        bounds = ((-0.2, -0.01, 1.3), (0.2, 0.02, 1.7))
        e = without("localized_geometric_change") + [
            evidence(
                prefix + "geo",
                "geometry",
                "positive",
                1,
                bounds_world_m=bounds,
                region_comparison_possible=True,
                spatial_reference="plant-01",
            ),
            evidence(
                prefix + "thermal",
                "thermal",
                "positive",
                2,
                bounds_world_m=bounds,
                region_comparison_possible=True,
                spatial_reference="plant-01",
            ),
        ]
        expected = "red"
    if case == 9:
        e = without("localized_geometric_change") + [
            evidence(prefix + "geo", "geometry", "positive", 1),
            evidence(prefix + "thermal", "thermal", "positive", 1, asset="DR-01"),
        ]
        expected = "amber"
    if case == 10:
        e = without("abnormal_process_pressure_residual") + [
            evidence(prefix + "residual", "residual", "positive", 1)
        ]
        e.extend(
            [
                e[-1],
                e[-1].model_copy(
                    update={
                        "evidence_id": prefix + "derived",
                        "source_id": prefix + "derived",
                        "algorithm": "static",
                        "origin_identity": e[-1].origin_identity,
                        "derived_from": [e[-1].origin_identity],
                    }
                ),
            ]
        )
        expected = "amber"
    if case == 11:
        e.append(evidence(prefix + "late", "pressure", "positive", 1, delay=30))
        at = START + timedelta(seconds=32)
        expected = "unknown"
    if case == 12:
        e = without("localized_geometric_change") + [
            evidence(prefix + "l2", "geometry", "inconclusive", 1)
        ]
        expected = "unknown"
    if case == 14:
        policy.requirements.append(
            MonitoringRequirement(
                requirement_id="global-structural-coverage",
                asset_id="BW-01",
                hypothesis="global_geometric_change",
                scope="global_wall",
                max_age_s=3600,
            )
        )
        expected = "unknown"
    if case == 15:
        e = without("abnormal_process_pressure_residual") + [
            evidence(prefix + "uncalibrated", "residual", "inconclusive", 1)
        ]
        expected = "unknown"
    if case == 16:
        e.append(
            evidence(
                prefix + "saturated",
                "thermal",
                "inconclusive",
                1,
                asset=None,
                quality_indicators={"saturated_pixels": 100, "total_pixels": 100},
            )
        )
        target = "inspection-context"
        expected = "unknown"
    if case == 17:
        e.append(evidence(prefix + "contradiction", "pressure", "negative", 1))
    if case == 18:
        e.extend([e[-1], e[-1]])
    if case == 19:
        e += [
            evidence(prefix + "recover1", "pressure", "negative", 4),
            evidence(prefix + "recover2", "pressure", "negative", 10),
            evidence(prefix + "temp-new", "temperature", "negative", 10),
            evidence(prefix + "ref-new", "residual", "negative", 10),
        ]
        at = START + timedelta(seconds=11)
        expected = "green"
    if case == 20:
        actions = [
            OperatorAction(
                action_id=prefix + "ack",
                asset_id="BW-01",
                hazard_id="critical-pressure",
                at=START + timedelta(seconds=3),
                kind="acknowledge",
                rationale="Synthetic operator reviewed; no recovery claimed",
            )
        ]
    if case == 21:
        e = without("critical_pressure_limit") + [
            evidence(prefix + "clock", "pressure", "negative", 1, clock_quality="unknown"),
            evidence(prefix + "future", "pressure", "positive", 50),
        ]
        expected = "unknown"
    if case == 22:
        e = [x for x in normal if x.sensor_id != "pressure-01"]
        expected = "unknown"
    # Vary valid transport latency while preserving event time/policy targets; duplicates remain exact.
    rng = random.Random(seed)
    for i, x in enumerate(e):
        shift = rng.uniform(0.0001, 0.02)
        if (
            x.clock_quality == "synchronized"
            and x.available_at <= at
            and x.evidence_id not in [v.evidence_id for v in e[:i]]
        ):
            e[i] = x.model_copy(
                update={
                    "processed_at": x.processed_at + timedelta(seconds=shift),
                    "available_at": x.available_at + timedelta(seconds=shift),
                }
            )
    # Restore retransmissions to identical canonical records.
    originals = {}
    for i, x in enumerate(e):
        if x.evidence_id in originals:
            e[i] = originals[x.evidence_id]
        else:
            originals[x.evidence_id] = x
    return (
        e,
        actions,
        policy,
        at,
        {
            "case": case,
            "seed": seed,
            "target_asset": target,
            "expected_severity": expected,
            "track": "controlled",
            "critical_event": case in [5, 6, 7, 8, 13, 17, 18, 19, 20],
        },
    )
