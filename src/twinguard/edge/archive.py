"""Optional bounded raw inbox archival with durable content hashes and dedup identity.

Scientific observations, F1 evidence/events/explanations and provenance remain in SQL.
Callers must back up the archive store together with PostgreSQL. Orphan CAS objects
on transaction rollback are harmless; SQL rows are deleted only after durable write.
"""

import gzip
import hashlib
import json
from datetime import timedelta
from sqlalchemy import select, delete
from .contracts import now
from .storage import inbox, jobs, put, audit, get
from .artifacts import ArtifactStore


def archive_raw(db, store_root, days=90, limit=256):
    if not 1 <= limit <= 256 or days < 0:
        raise ValueError("Archive requires nonnegative retention and 1..256 row batch")
    store = ArtifactStore(store_root)
    cutoff = (now() - timedelta(days=days)).isoformat()
    with db.begin() as c:
        # Never move a message while its durable work is unresolved.
        q = (
            select(inbox)
            .where(
                inbox.c.received < cutoff,
                ~inbox.c.id.in_(select(jobs.c.id).where(jobs.c.status != "completed")),
            )
            .order_by(inbox.c.received, inbox.c.id)
            .limit(limit)
        )
        if c.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        rows = [dict(row) for row in c.execute(q).mappings()]
        if not rows:
            return {"rows": 0, "raw_bytes": 0, "archive_bytes": 0, "sha256": None}
        raw = (
            b"\n".join(
                json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                for row in rows
            )
            + b"\n"
        )
        compressed = gzip.compress(raw, mtime=0)
        digest = store.persist(compressed)
        for index, row in enumerate(rows):
            put(
                c,
                "archive",
                row["id"],
                {
                    "digest": row["digest"],
                    "source": row["source"],
                    "received": row["received"],
                    "archive_sha256": digest,
                    "archive_row": index,
                    "format": "gzip-jsonl-v1",
                },
            )
        c.execute(delete(inbox).where(inbox.c.id.in_([row["id"] for row in rows])))
        audit(
            c,
            "raw_archive_externalized",
            count=len(rows),
            days=days,
            archive_sha256=digest,
            raw_bytes=len(raw),
            archive_bytes=len(compressed),
        )
    return {
        "rows": len(rows),
        "raw_bytes": len(raw),
        "archive_bytes": len(compressed),
        "sha256": digest,
    }


def recover_raw(connection, message_id, store_root):
    record = get(connection, "archive", message_id)
    if not record or record.get("format") != "gzip-jsonl-v1":
        raise ValueError("Missing supported archive reference")
    data = ArtifactStore(store_root).path(record["archive_sha256"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != record["archive_sha256"]:
        raise ValueError("Archive checksum mismatch")
    rows = gzip.decompress(data).splitlines()
    row = json.loads(rows[record["archive_row"]])
    if row["id"] != message_id or row["digest"] != record["digest"]:
        raise ValueError("Archive identity mismatch")
    return row
