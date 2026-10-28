"""Transactional durable inbox/jobs/state/outbox; SQLite only for isolated unit tests."""

import os
from functools import lru_cache
import uuid
from datetime import timedelta
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    String,
    Text,
    Integer,
    JSON,
    Float,
    select,
    and_,
    delete,
)
from .contracts import now

metadata = MetaData()
records = Table(
    "records",
    metadata,
    Column("kind", String(40), primary_key=True),
    Column("id", String(256), primary_key=True),
    Column("asset", String(128), index=True),
    Column("at", String(40), index=True),
    Column("body", JSON, nullable=False),
)
inbox = Table(
    "inbox",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("source", String(128), index=True),
    Column("digest", String(64)),
    Column("status", String(30)),
    Column("received", String(40)),
    Column("body", JSON),
)
observations = Table(
    "observations",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("asset", String(128), index=True),
    Column("sensor", String(128), index=True),
    Column("acquired", String(40), index=True),
    Column("received", String(40)),
    Column("source", String(128)),
    Column("body", JSON),
    Column("metadata", JSON),
)
jobs = Table(
    "jobs",
    metadata,
    Column("id", String(256), primary_key=True),
    Column("kind", String(30), index=True),
    Column("status", String(30), index=True),
    Column("attempts", Integer, default=0),
    Column("lease_until", String(40)),
    Column("owner", String(80)),
    Column("created", String(40)),
    Column("body", JSON),
    Column("error", Text),
    Column("duration_s", Float),
)
stream = Table(
    "stream",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("at", String(40)),
    Column("kind", String(40)),
    Column("body", JSON),
)


@lru_cache(maxsize=8)
def _cached_engine(url):
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def engine(url=None):
    return _cached_engine(url or os.environ.get("TWINGUARD_DB", "sqlite:////tmp/twinguard-edge.db"))


def get(c, kind, ident, lock=False):
    q = select(records.c.body).where(and_(records.c.kind == kind, records.c.id == ident))
    if lock:
        q = q.with_for_update()
    return c.execute(q).scalar_one_or_none()


def put(c, kind, ident, body, asset=None, at=None):
    values = dict(kind=kind, id=ident, body=body, asset=asset, at=at or now().isoformat())
    dialect = c.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    c.execute(
        insert(records)
        .values(**values)
        .on_conflict_do_update(index_elements=[records.c.kind, records.c.id], set_=values)
    )


def audit(c, reason, **body):
    put(c, "audit", str(uuid.uuid4()), {"reason": reason, "at": now().isoformat(), **body})


def emit(c, kind, body):
    c.execute(stream.insert().values(at=now().isoformat(), kind=kind, body=body))


def list_records(c, kind, asset=None, limit=100, offset=0):
    q = select(records.c.body).where(records.c.kind == kind)
    if asset:
        q = q.where(records.c.asset == asset)
    return list(
        c.execute(
            q.order_by(records.c.at.desc(), records.c.id).limit(limit).offset(offset)
        ).scalars()
    )


def enqueue(c, ident, kind, body):
    if c.execute(select(jobs.c.id).where(jobs.c.id == ident)).first() is None:
        c.execute(
            jobs.insert().values(
                id=ident,
                kind=kind,
                status="pending",
                attempts=0,
                created=now().isoformat(),
                body=body,
            )
        )


def claim(db, kind, owner, lease_s=120, retry_limit=3):
    with db.begin() as c:
        q = (
            select(jobs)
            .where(
                jobs.c.kind == kind,
                jobs.c.attempts < retry_limit,
                (
                    (jobs.c.status == "pending")
                    | ((jobs.c.status == "processing") & (jobs.c.lease_until < now().isoformat()))
                ),
            )
            .order_by(jobs.c.created)
            .limit(1)
        )
        if c.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        row = c.execute(q).mappings().first()
        if not row:
            return None
        c.execute(
            jobs.update()
            .where(jobs.c.id == row["id"])
            .values(
                status="processing",
                owner=owner,
                attempts=row["attempts"] + 1,
                lease_until=(now() + timedelta(seconds=lease_s)).isoformat(),
            )
        )
        return dict(row)


def retain(db, days=90, limit=1000):
    """Archive bounded raw records. Preserve scientific references and unresolved history."""
    cutoff = (now() - timedelta(days=days)).isoformat()
    with db.begin() as c:
        ids = list(
            c.execute(select(inbox.c.id).where(inbox.c.received < cutoff).limit(limit)).scalars()
        )
        for ident in ids:
            row = dict(c.execute(select(inbox).where(inbox.c.id == ident)).mappings().one())
            put(c, "archive", ident, row)
        if ids:
            c.execute(delete(inbox).where(inbox.c.id.in_(ids)))
        audit(c, "retention_archived", count=len(ids), days=days)
    return len(ids)
