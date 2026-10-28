"""Verified public analysis ingestion and evidence artifact persistence."""

from pathlib import Path
from datetime import datetime
import hashlib
import json
from twinguard.core.analytics_contracts import (
    GeometryResult,
    RegistrationResult,
    ThermalResult,
    OperatingPrediction,
)
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations
from .models import FusionEvidence, ProcessingRecord, FusionEvidenceManifest
from . import adapters
from .policies import policy_hash


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value.model_dump(mode="json") if hasattr(value, "model_dump") else value,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def save_evidence(output, records, provenance):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    save(output / "evidence.json", [e.model_dump(mode="json") for e in records])
    digest = hashlib.sha256((output / "evidence.json").read_bytes()).hexdigest()
    save(
        output / "manifest.json",
        {
            "schema_version": "1.0.0",
            "kind": "FusionEvidenceManifest",
            "evidence_uri": "evidence.json",
            "sha256": digest,
            "count": len(records),
            "provenance": provenance,
        },
    )


def read_evidence(directory):
    root = Path(directory)
    manifest = FusionEvidenceManifest.model_validate_json(
        (root / "manifest.json").read_text()
    ).model_dump()
    path = (root / manifest["evidence_uri"]).resolve()
    if not path.is_relative_to(root.resolve()) or "evaluation_private" in path.parts:
        raise ValueError("Unsafe evidence path")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Evidence checksum mismatch")
    records = [FusionEvidence.model_validate(r) for r in json.loads(path.read_text())]
    if len(records) != manifest["count"]:
        raise ValueError("Evidence count mismatch")
    return records


def seal_public_predictions(directory):
    files = {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
        and "evaluation_private" not in p.parts
        and p.name != "predictions_ready.json"
    }
    save(
        directory / "predictions_ready.json", {"kind": "FusionPredictionsSeal", "artifacts": files}
    )


def write_run(output, state, history, policy, metadata):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Fusion run output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    from twinguard import __version__

    snapshot = [
        e.model_dump(mode="json")
        for e in sorted(state.evidence.values(), key=lambda e: e.evidence_id)
    ]
    save(output / "evidence.json", snapshot)
    save(
        output / "input_manifest.json",
        {
            "kind": "FusionRunInputSnapshot",
            "count": len(snapshot),
            "sha256": hashlib.sha256((output / "evidence.json").read_bytes()).hexdigest(),
            "evidence_uri": "evidence.json",
            "scope": "Evidence delivered to this state by the replay horizon; original stream URI retained in metadata",
        },
    )
    save(
        output / "processing_metrics.json",
        {
            "evidence_count": len(snapshot),
            "decision_count": len(history),
            "notice_count": len(state.notices),
            "processing_runtime_s": metadata.get("processing_runtime_s"),
        },
    )
    save(
        output / "provenance.json",
        {
            "software_version": __version__,
            "policy_sha256": policy_hash(policy),
            "source_provenance_ids": sorted({e.provenance_id for e in state.evidence.values()}),
            "availability_bases": sorted({e.availability_basis for e in state.evidence.values()}),
        },
    )
    save(output / "state.json", state)
    save(output / "history.json", [d.model_dump(mode="json") for d in history])
    save(output / "assessments.json", [d.assessment.model_dump(mode="json") for d in history])
    save(output / "advisories.json", [n.model_dump(mode="json") for n in state.notices])
    save(output / "events.json", [e.model_dump(mode="json") for e in state.events.values()])
    save(output / "policy.json", policy)
    save(output / "metadata.json", {"policy_sha256": policy_hash(policy), **metadata})
    seal_public_predictions(output)


def prepare(analysis_run, policy, clock_quality="unknown"):
    root = Path(analysis_run)
    seal_path = root / "predictions_ready.json"
    if not seal_path.is_file():
        raise ValueError("Prepare requires a public sealed Phase 3/3.1 prediction directory")
    seal = json.loads(seal_path.read_text())
    for relative, digest in seal["artifacts"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or "evaluation_private" in path.parts:
            raise ValueError("Unsafe source artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Modified analysis artifact")
    public = seal["public_inputs"]
    dataset = public.get("public_dataset") or public.get("dataset")
    if dataset is None and "current" in public:
        dataset = next(
            (p for p in Path(public["current"]).parents if (p / "manifest.json").is_file()), None
        )
    if dataset is None:
        raise ValueError("Public observation manifest reference is required")
    records = load_public_observations(Path(dataset))
    by_id = {getattr(r, "capture_id", getattr(r, "observation_id", "")): r for r in records}
    available = datetime.fromisoformat(seal["finished_at"])
    result = []
    for relative in sorted(seal["artifacts"]):
        path = root / relative
        if path.name == "geometry.json":
            g = GeometryResult.model_validate_json(path.read_text())
            reg = RegistrationResult.model_validate_json(
                (path.parent / "registration.json").read_text()
            )
            source = by_id[g.current_capture_id]
            processing = ProcessingRecord(
                source_id=g.analysis_id,
                received_at=source.received_at,
                processed_at=max(available, source.received_at),
                available_at=max(available, source.received_at),
                basis="recorded",
                clock_quality=clock_quality,
                rationale="Offline public prediction seal completion; acquisition clock separately declared",
            )
            result.extend(adapters.geometry(g, reg, processing, source.provenance_id))
        elif path.suffix == ".json" and path.name.startswith("operating-"):
            for raw in json.loads(path.read_text()):
                p = OperatingPrediction.model_validate(raw)
                source = by_id[p.observation_id]
                processing = ProcessingRecord(
                    source_id=p.prediction_id,
                    received_at=source.received_at,
                    processed_at=max(available, p.available_at),
                    available_at=max(available, p.available_at),
                    basis="recorded",
                    clock_quality=clock_quality,
                    rationale="Offline seal completion",
                )
                result.append(adapters.operating(p, source, processing))
        elif path.suffix == ".json" and path.parent.name in ["conditioned", "static"]:
            raw = json.loads(path.read_text())
            if "saturation_known" not in raw:
                continue
            t = ThermalResult.model_validate(raw)
            source = by_id[t.capture_id]
            processing = ProcessingRecord(
                source_id=t.analysis_id,
                received_at=source.received_at,
                processed_at=max(available, source.received_at),
                available_at=max(available, source.received_at),
                basis="recorded",
                clock_quality=clock_quality,
                rationale="Offline seal completion",
            )
            result.extend(adapters.thermal(t, processing, source.provenance_id))
    for source in records:
        if isinstance(source, InspectionCapture):
            continue
        processing = ProcessingRecord(
            source_id=source.observation_id,
            received_at=source.received_at,
            processed_at=max(available, source.received_at),
            available_at=max(available, source.received_at),
            basis="recorded",
            clock_quality=clock_quality,
            rationale="Public measurements ingested at this offline prepare run",
        )
        value = adapters.engineering_limit(source, processing, policy)
        if value:
            result.append(value)
    return result
