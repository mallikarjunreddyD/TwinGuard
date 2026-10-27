"""Pure adapter to existing evidence records, without a fusion or hazard policy."""

from twinguard.core.contracts import EvidenceRecord


def operating_evidence(prediction, processed_at, provenance_id):
    status = (
        "valid"
        if prediction.status == "valid"
        else "invalid"
        if prediction.status == "invalid"
        else "inconclusive"
    )
    return EvidenceRecord(
        evidence_id="evidence-" + prediction.prediction_id,
        asset_id=prediction.asset_id,
        source_id=prediction.prediction_id,
        modality="fixed_sensor",
        acquired_at=prediction.acquired_at,
        processed_at=processed_at,
        hypothesis_id="operating_residual",
        quality="good" if status == "valid" else "unknown",
        uncertainty=prediction.uncertainty_score,
        uncertainty_unit=prediction.unit if prediction.uncertainty_score is not None else None,
        operating_context_id=prediction.model_id,
        validity=status,
        provenance_id=provenance_id,
    )
