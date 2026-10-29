"""Actual queue admission fault injection; fixture jobs are not sensor observations.

Inject exactly 10000 pending fixture jobs to exercise the configured global admission
limit through real MQTT. Remove only these fixture jobs after the test. The result
is a capacity-boundary check, not a sustained 10000-observation throughput claim.
"""

from pathlib import Path
import hashlib
import json
import time
import uuid
from sqlalchemy import create_engine, select, delete, func
from twinguard.edge.storage import jobs, records, observations
from twinguard.edge.contracts import Envelope, now
from twinguard.edge.protocols import publish
from twinguard.core.contracts import SensorObservation
from twinguard.core.observations import load_public_observations

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/mnt/d/TwinGuard/phase7-V4-queue-reservation-retest")


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    db = create_engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@localhost:18982/twinguard"
    )
    prefix = "p7-capacity-fixture-" + uuid.uuid4().hex + "-"
    dataset = ROOT / "experiments/outputs/e4-public-18010"
    public = list(load_public_observations(dataset))
    normal = next(
        r
        for r in public
        if isinstance(r, SensorObservation)
        and r.sensor_id == "pressure-01"
        and r.quality == "good"
        and r.value < 1150000
    )
    critical = next(
        r
        for r in public
        if isinstance(r, SensorObservation)
        and r.sensor_id == "pressure-01"
        and r.quality == "good"
        and r.value >= 1150000
    )
    report = {
        "scope": __doc__,
        "started_at": now().isoformat(),
        "injected_fixture_jobs": 10000,
        "messages": [],
    }
    ids = [prefix + str(i) for i in range(10000)]
    try:
        with db.begin() as c:
            c.execute(
                jobs.insert(),
                [
                    {
                        "id": ident,
                        "kind": "capacity_fixture",
                        "status": "pending",
                        "attempts": 0,
                        "created": now().isoformat(),
                        "body": {
                            "fault_injection": "Phase7 queue capacity, not a scientific observation"
                        },
                    }
                    for ident in ids
                ],
            )
            report["measured_pending_before_publish"] = c.execute(
                select(func.count()).select_from(jobs).where(jobs.c.status == "pending")
            ).scalar_one()
        envelopes = []
        for index, (kind, sample) in enumerate((("ordinary", normal), ("critical", critical))):
            sample = sample.model_copy(update={"observation_id": prefix + kind})
            at = now()
            env = Envelope(
                message_id=prefix + kind,
                source_id="demo-iot",
                sequence=index,
                sequence_epoch=prefix,
                emitted_at=at,
                provenance_id=sample.provenance_id,
                mode="simulation_replay",
                replay_acquired_at=at,
                observation=sample,
            )
            envelopes.append(env)
            report["messages"].append(
                {
                    "kind": kind,
                    "message_id": env.message_id,
                    "observation_id": sample.observation_id,
                    "wire_sha256": hashlib.sha256(env.model_dump_json().encode()).hexdigest(),
                    "emitted_at": at.isoformat(),
                }
            )
        report["pubacks"] = publish(envelopes, secrets["demo-iot"], port=18983)
        time.sleep(3)
        with db.connect() as c:
            audits = list(
                c.execute(select(records.c.body).where(records.c.kind == "audit")).scalars()
            )
            for row in report["messages"]:
                row["persisted"] = c.execute(
                    select(func.count())
                    .select_from(observations)
                    .where(observations.c.id == row["observation_id"])
                ).scalar_one()
                row["quarantine"] = [a for a in audits if a.get("digest") == row["wire_sha256"]]
        critical_row = next(r for r in report["messages"] if r["kind"] == "critical")
        with db.connect() as c:
            timing = c.execute(
                select(records.c.body).where(
                    records.c.kind == "timing", records.c.id == critical_row["observation_id"]
                )
            ).scalar_one_or_none()
            if timing:
                trace_rows = list(
                    c.execute(
                        select(records.c.body).where(
                            records.c.kind == "trace", records.c.id.in_(timing["assessments"])
                        )
                    ).scalars()
                )
                report["critical_temporal_states"] = [
                    t["status"]
                    for tr in trace_rows
                    for t in tr["temporal"]
                    if t["evidence_id"] == "limit-" + critical_row["observation_id"]
                    and t["hazard_id"] == "critical-pressure"
                ]
        extra = [prefix + "reserve-bound-" + str(i) for i in range(100)]
        with db.begin() as c:
            c.execute(
                jobs.insert(),
                [
                    {
                        "id": ident,
                        "kind": "capacity_fixture",
                        "status": "pending",
                        "attempts": 0,
                        "created": now().isoformat(),
                        "body": {"fault_injection": "reserved queue total bound"},
                    }
                    for ident in extra
                ],
            )
        ids.extend(extra)
        at = now()
        sample = critical.model_copy(update={"observation_id": prefix + "beyond-total"})
        beyond = Envelope(
            message_id=sample.observation_id,
            source_id="demo-iot",
            sequence=2,
            sequence_epoch=prefix,
            emitted_at=at,
            provenance_id=sample.provenance_id,
            mode="simulation_replay",
            replay_acquired_at=at,
            observation=sample,
        )
        report["total_bound_puback"] = publish([beyond], secrets["demo-iot"], port=18983)
        time.sleep(1)
        with db.connect() as c:
            report["beyond_total_limit_persisted"] = c.execute(
                select(func.count())
                .select_from(observations)
                .where(observations.c.id == sample.observation_id)
            ).scalar_one()
        report["status"] = "executed"
        report["critical_capacity_boundary"] = (
            "Ordinary admission rejects at 10000; only independently current authoritative critical observations may use the bounded reserve"
        )
    finally:
        with db.begin() as c:
            result = c.execute(delete(jobs).where(jobs.c.id.in_(ids)))
            report["removed_fixture_jobs"] = result.rowcount
        report["finished_at"] = now().isoformat()
        (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
