"""Accelerated raw-message retention on the new Phase7 DB; scientific state retained."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time
from sqlalchemy import create_engine, text
from twinguard.edge.archive import archive_raw, recover_raw
from twinguard.edge.contracts import Envelope
from twinguard.edge.ingestion import ingest, topic

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/outputs/phase7-V5-archive-validation"


def signature(c):
    result = {}
    for kind in (
        "evidence",
        "event",
        "trace",
        "condition",
        "processing",
        "policy",
        "source",
        "inspection_result",
        "inspection_plan",
    ):
        hashes = (
            c.execute(
                text("SELECT md5(body::text) FROM records WHERE kind=:kind ORDER BY id"),
                {"kind": kind},
            )
            .scalars()
            .all()
        )
        result[kind] = {
            "count": len(hashes),
            "sha256": hashlib.sha256("".join(hashes).encode()).hexdigest(),
        }
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    db = create_engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@localhost:18982/twinguard"
    )
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Explicit days=0 accelerated retention on Phase7 test DB, not 90-day endurance",
        "batches": [],
        "concurrent_source_writes": "May change history hashes; scientific row identifiers are independently checked for deletion",
    }
    with db.connect() as c:
        report["before"] = signature(c)
        retained = list(
            c.execute(
                text(
                    "SELECT kind,id FROM records WHERE kind IN ('evidence','event','trace','processing','source','inspection_plan','inspection_result')"
                )
            )
        )
        report["before_database_bytes"] = c.execute(
            text("SELECT pg_database_size(current_database())")
        ).scalar_one()
        report["before_inbox_logical_bytes"] = c.execute(
            text("SELECT coalesce(sum(octet_length(body::text)),0) FROM inbox")
        ).scalar_one()
    started = time.perf_counter()
    for _ in range(20):
        result = archive_raw(db, OUT / "archives", days=0, limit=256)
        report["batches"].append(result)
        if not result["rows"]:
            break
    report["archiving_s"] = time.perf_counter() - started
    with db.connect() as c:
        report["after"] = signature(c)
        report["after_database_bytes"] = c.execute(
            text("SELECT pg_database_size(current_database())")
        ).scalar_one()
        report["after_inbox_logical_bytes"] = c.execute(
            text("SELECT coalesce(sum(octet_length(body::text)),0) FROM inbox")
        ).scalar_one()
        current = set(c.execute(text("SELECT kind,id FROM records")))
        report["retained_scientific_rows"] = len(retained)
        report["deleted_scientific_rows"] = sum(row not in current for row in retained)
        ids = (
            c.execute(
                text(
                    "SELECT id FROM records WHERE kind='archive' AND body->>'format'='gzip-jsonl-v1' ORDER BY id LIMIT 20"
                )
            )
            .scalars()
            .all()
        )
        recovered = [recover_raw(c, ident, OUT / "archives") for ident in ids]
    report["recovered_samples"] = len(recovered)
    report["duplicate_replays"] = []
    for row in recovered[:3]:
        envelope = Envelope.model_validate(row["body"])
        raw = envelope.model_dump_json().encode()
        if hashlib.sha256(raw).hexdigest() == row["digest"]:
            result = ingest(
                db,
                raw,
                envelope.source_id,
                topic(envelope.source_id, envelope.site_id, envelope.kind),
            )
            report["duplicate_replays"].append(result)
        else:
            report["duplicate_replays"].append(
                {"status": "wire_serialization_not_reconstructible", "id": row["id"]}
            )
    report["raw_bytes"] = sum(r["raw_bytes"] for r in report["batches"])
    report["archive_bytes"] = sum(r["archive_bytes"] for r in report["batches"])
    report["archived_rows"] = sum(r["rows"] for r in report["batches"])
    report["status"] = (
        "passed"
        if report["deleted_scientific_rows"] == 0
        and report["recovered_samples"] > 0
        and all(r["status"] == "duplicate" for r in report["duplicate_replays"])
        else "partial"
    )
    report["limitations"] = [
        "MVCC relation allocation may grow despite smaller logical payload; VACUUM FULL not run during live stress",
        "SQL F1 trace/evidence growth remains and is included in projections",
        "Archive directory is mandatory in backup/restore",
    ]
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(report["status"], report["archived_rows"], report["raw_bytes"], report["archive_bytes"])


if __name__ == "__main__":
    main()
