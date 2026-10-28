"""Local authorized maintenance commands; no scientific payload edits or policy overrides."""

import argparse
from sqlalchemy import select
from .storage import engine, jobs, audit, retain


def retry_failed(db, ident, rationale):
    with db.begin() as c:
        row = (
            c.execute(select(jobs).where(jobs.c.id == ident).with_for_update())
            .mappings()
            .one_or_none()
        )
        if not row or row["status"] != "failed":
            raise ValueError("Only failed durable jobs can be explicitly retried")
        audit(
            c,
            "authorized_job_retry",
            job_id=ident,
            prior_attempts=row["attempts"],
            prior_error=row["error"],
            actor="local-administrator",
            rationale=rationale,
        )
        c.execute(
            jobs.update()
            .where(jobs.c.id == ident)
            .values(status="pending", attempts=0, owner=None, lease_until=None)
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["retry", "archive"])
    p.add_argument("--job-id")
    p.add_argument("--rationale", default="Reviewed failed job after correcting service dependency")
    p.add_argument("--days", type=int, default=90)
    a = p.parse_args()
    if a.command == "retry":
        retry_failed(engine(), a.job_id, a.rationale)
    else:
        print("Archived raw inbox records:", retain(engine(), a.days))
