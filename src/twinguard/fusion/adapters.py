"""Pure adapters from public Phase 3 outputs; availability is always explicit."""

from .models import FusionEvidence


def timing(processing, acquired, source):
    if processing.source_id != source or processing.received_at < acquired:
        raise ValueError("Processing record must bind the source and follow acquisition")
    return dict(
        acquired_at=acquired,
        received_at=processing.received_at,
        available_at=processing.available_at,
        processed_at=processing.processed_at,
        availability_basis=processing.basis,
        clock_quality=processing.clock_quality,
        clock_uncertainty_s=processing.clock_uncertainty_s,
    )


def geometry(result, registration, processing, provenance_id):
    time = timing(processing, result.acquired_at, result.analysis_id)
    if (
        result.registration_id != registration.registration_id
        or result.current_capture_id != registration.current_capture_id
        or result.baseline_capture_id != registration.baseline_capture_id
    ):
        raise ValueError("Geometry/registration source mismatch")
    calibrated = not result.calibration_id.startswith("uncalibrated")
    records = []
    patches = {p.patch_id: p for p in result.patches}
    for asset, status in sorted(result.asset_statuses.items()):
        regions = [
            r
            for r in result.regions
            if r.asset_id == asset and r.association_status == "associated"
        ]
        usable = []
        for region in regions:
            local = [patches[key] for key in region.patch_ids if key in patches]
            if (
                local
                and len(local) == len(region.patch_ids)
                and all(
                    p.status == "valid"
                    and p.significant is True
                    and p.displacement_m is not None
                    and (
                        result.measurement_basis != "localized_relative"
                        or p.calibration_support >= 10
                    )
                    for p in local
                )
            ):
                usable.append(region)
        valid = (
            result.status == "valid"
            and status == "valid"
            and registration.status == "valid"
            and calibrated
        )
        if result.measurement_basis == "localized_relative" and not any(
            p.asset_id == asset and p.status == "valid" and p.calibration_support >= 10
            for p in result.patches
        ):
            valid = False
        if regions and len(usable) != len(regions):
            valid = False
        for region in usable if valid and usable else [None]:
            finding = (
                "positive"
                if region
                else "negative"
                if valid
                and result.significant is not None
                and not regions
                and (not result.significant or bool(result.regions))
                else "inconclusive"
            )
            if registration.status != "valid":
                finding = "unavailable"
            if not valid and finding in ["positive", "negative"]:
                finding = "inconclusive"
            frame = (
                registration.registered_coordinate_frame.reference_id
                if registration.registered_coordinate_frame
                else None
            )
            records.append(
                FusionEvidence(
                    evidence_id="fusion-"
                    + result.analysis_id
                    + "-"
                    + asset
                    + "-"
                    + (region.region_id if region else "summary"),
                    source_id=result.analysis_id,
                    modality="geometric",
                    algorithm=result.method,
                    algorithm_version=result.algorithm_version,
                    provenance_id=provenance_id,
                    asset_id=asset,
                    capture_ids=[result.baseline_capture_id, result.current_capture_id],
                    model_id=result.calibration_id,
                    **time,
                    hypothesis="localized_geometric_change",
                    finding=finding,
                    value=region.representative_displacement_m if region else None,
                    unit="m",
                    uncertainty_score=region.uncertainty_score_m if region else None,
                    scope="localized_wall",
                    measurement_basis=result.measurement_basis,
                    qualification_status="valid" if valid else status,
                    association="associated",
                    region_id=region.region_id if region else None,
                    bounds_world_m=region.bounds_world_m if region else None,
                    spatial_reference=frame,
                    region_comparison_possible=bool(region and frame),
                    origin_identity=result.baseline_capture_id + "-" + result.current_capture_id,
                    dependence_group="scan-" + result.current_capture_id,
                    derived_from=[result.baseline_capture_id, result.current_capture_id],
                    shared_references=[result.calibration_id, result.reference_id],
                    quality="good" if valid else "unknown",
                    calibration_valid=calibrated,
                    registration_valid=registration.status == "valid",
                    coverage_status=status,
                    reasons=result.quality_flags
                    + (
                        []
                        if valid
                        else [
                            "unavailable_registration_coverage_calibration_or_patch_qualification"
                        ]
                    ),
                    quality_indicators={
                        "calibration_support": min(
                            [patches[k].calibration_support for k in region.patch_ids], default=0
                        )
                        if region
                        else 0
                    },
                    reinspection_candidate=result.reinspection_candidate or not valid,
                )
            )
    return records


def thermal(result, processing, provenance_id):
    time = timing(processing, result.acquired_at, result.analysis_id)
    valid = (
        result.status == "valid"
        and result.saturation_known
        and result.valid_pixels > 0
        and not result.model_id.startswith("uncalibrated")
    )
    records = []
    for region in result.regions if result.regions and valid else [None]:
        finding = (
            "positive"
            if valid and region
            else "negative"
            if valid and result.significant is False
            else "inconclusive"
        )
        records.append(
            FusionEvidence(
                evidence_id="fusion-"
                + result.analysis_id
                + "-"
                + (region.region_id if region else "summary"),
                source_id=result.analysis_id,
                modality="thermal",
                algorithm=result.method,
                algorithm_version="v1",
                provenance_id=provenance_id,
                asset_id=region.asset_id
                if region and region.association_status == "associated"
                else None,
                capture_ids=[result.capture_id],
                model_id=result.model_id,
                **time,
                hypothesis="abnormal_thermal_residual",
                finding=finding,
                value=region.peak_residual_c if region else None,
                residual=region.peak_residual_c if region else None,
                unit="degC",
                uncertainty_score=region.uncertainty_score_c if region else None,
                scope="apparent_image_temperature",
                measurement_basis="apparent_radiometric",
                qualification_status="valid" if valid else result.status,
                association=region.association_status if region else "image_only",
                image_bounds=region.image_bounds if region else None,
                origin_identity=result.capture_id,
                dependence_group="image-" + result.capture_id,
                derived_from=[result.capture_id],
                shared_references=[result.model_id],
                quality="good" if valid else "unknown",
                calibration_valid=valid,
                coverage_status=result.status,
                quality_indicators={
                    "valid_pixels": result.valid_pixels,
                    "saturated_pixels": result.saturated_pixels,
                    "total_pixels": result.total_pixels,
                    "saturation_known": result.saturation_known,
                },
                reasons=result.quality_flags
                + ["Image-space context cannot establish physical region overlap"],
                reinspection_candidate=not valid or bool(region),
            )
        )
    return records


def operating(prediction, observation, processing):
    if (
        prediction.observation_id != observation.observation_id
        or prediction.sensor_id != observation.sensor_id
        or prediction.asset_id != observation.asset_id
        or prediction.acquired_at != observation.acquired_at
        or prediction.unit != observation.unit
        or prediction.observed_value != observation.value
    ):
        raise ValueError("Prediction must match the actual public source observation")
    time = timing(processing, observation.acquired_at, prediction.prediction_id)
    if (
        processing.available_at < prediction.available_at
        or processing.received_at < observation.received_at
    ):
        raise ValueError("Availability cannot precede source prediction/observation")
    valid = (
        prediction.status == "valid"
        and observation.quality == "good"
        and prediction.significant is not None
    )
    finding = (
        ("positive" if prediction.significant else "negative")
        if valid
        else "invalid"
        if observation.quality == "invalid"
        else "inconclusive"
    )
    return FusionEvidence(
        evidence_id="fusion-" + prediction.prediction_id,
        source_id=prediction.prediction_id,
        modality="fixed_sensor",
        algorithm=prediction.method,
        algorithm_version="v1",
        provenance_id=observation.provenance_id,
        asset_id=prediction.asset_id,
        sensor_id=prediction.sensor_id,
        model_id=prediction.model_id,
        **time,
        hypothesis=(
            "abnormal_surface_temperature_residual"
            if observation.measurement_source == "surface"
            and observation.measurement_type == "temperature"
            else "abnormal_process_" + observation.measurement_type + "_residual"
        ),
        finding=finding,
        value=prediction.residual,
        observed_value=prediction.observed_value,
        estimated_reference=prediction.estimated_reference,
        residual=prediction.residual,
        unit=prediction.unit,
        uncertainty_score=prediction.uncertainty_score,
        scope="operating_reference",
        measurement_basis="calibrated_operating_residual",
        qualification_status="valid" if valid else prediction.status,
        association="associated",
        origin_identity=observation.observation_id,
        dependence_group="sensor-" + observation.sensor_id,
        derived_from=[observation.observation_id],
        shared_references=[prediction.model_id],
        quality="good"
        if valid
        else observation.quality
        if observation.quality != "good"
        else "unknown",
        calibration_valid=valid,
        coverage_status=prediction.status,
        reasons=prediction.quality_flags,
    )


def engineering_limit(observation, processing, policy):
    authority = next((s for s in policy.authorities if s.sensor_id == observation.sensor_id), None)
    if observation.measurement_type not in ["pressure", "temperature"]:
        return None
    time = timing(processing, observation.acquired_at, observation.observation_id)
    if processing.received_at < observation.received_at:
        raise ValueError("Receipt cannot precede public arrival")
    reasons = []
    valid = True
    if (
        authority is None
        or authority.asset_id != observation.asset_id
        or authority.measurement_type != observation.measurement_type
        or authority.unit != observation.unit
    ):
        valid = False
        reasons.append("Unknown/mismatched sensor installation or units")
    if authority is None or authority.critical_limit is None:
        valid = False
        reasons.append(
            "Engineering limit unconfigured; no safety threshold inferred from residuals"
        )
    if authority and authority.calibration_status not in (
        ["verified", "assumed_simulation"]
        if policy.deployment_mode == "illustrative_simulation"
        else ["verified"]
    ):
        valid = False
        reasons.append("Instrument calibration not established for this deployment")
    value = observation.value if isinstance(observation.value, (int, float)) else None
    if (
        observation.quality != "good"
        or value is None
        or (authority and not authority.measurement_min <= value <= authority.measurement_max)
    ):
        valid = False
        reasons.append("Invalid/degraded or out-of-instrument-range reading")
    crossing = bool(valid and value >= authority.critical_limit)
    return FusionEvidence(
        evidence_id="limit-" + observation.observation_id,
        source_id=observation.observation_id,
        modality="fixed_sensor",
        algorithm="engineering_limit",
        algorithm_version=policy.version,
        provenance_id=observation.provenance_id,
        asset_id=observation.asset_id,
        sensor_id=observation.sensor_id,
        **time,
        model_id=policy.policy_id,
        hypothesis="critical_" + observation.measurement_type + "_limit",
        finding=("positive" if crossing else "negative")
        if valid
        else "invalid"
        if observation.quality == "invalid"
        else "inconclusive",
        value=value,
        observed_value=value,
        unit=observation.unit,
        uncertainty_score=observation.uncertainty,
        scope="engineering_limit",
        measurement_basis="configured_instrument_reading",
        qualification_status="valid" if valid else "unsupported",
        association="associated" if authority else "unknown",
        origin_identity=observation.observation_id,
        dependence_group="sensor-" + observation.sensor_id,
        derived_from=[observation.observation_id],
        shared_references=["instrument-" + observation.sensor_id],
        quality="good"
        if valid
        else observation.quality
        if observation.quality != "good"
        else "unknown",
        calibration_valid=valid,
        quality_indicators={
            "source_quality": observation.quality,
            "instrument_calibration": authority.calibration_status if authority else "unknown",
        },
        coverage_status="valid" if valid else "unsupported",
        reasons=reasons,
        authoritative_limit=valid,
        recovery_eligible=bool(valid and value <= authority.critical_limit - authority.hysteresis),
    )
