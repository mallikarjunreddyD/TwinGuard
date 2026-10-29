"""Actual browser audit chain and duplicate/restart checks after reviewed reinspection."""

from pathlib import Path
import json
import subprocess
import time
from sqlalchemy import create_engine, select, func
from edge_browser import run
from twinguard.edge.contracts import Envelope, now
from twinguard.edge.protocols import publish
from twinguard.edge.storage import records, jobs

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/mnt/d/TwinGuard/phase7-V7-browser-and-recovery")


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    db = create_engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@localhost:19082/twinguard"
    )
    envelope = Envelope.model_validate_json(
        Path("/mnt/d/TwinGuard/phase7-V7-reviewed-reinspection/delivery-envelope.json").read_text()
    )

    def event_ids():
        with db.connect() as c:
            return set(c.execute(select(records.c.id).where(records.c.kind == "event")).scalars())

    before = event_ids()
    report = {
        "started_at": now().isoformat(),
        "scope": "Actual software browser/operator simulation and durable duplicate/restart test; no physical flight or human/site acceptance",
    }
    try:
        report["duplicate_pubacks"] = publish([envelope, envelope], secrets["demo-uav"], port=19083)
        time.sleep(1)
        subprocess.run(
            ["docker", "restart", "twinguard-phase7-corrected-fast-worker-1"],
            check=True,
            capture_output=True,
        )
        time.sleep(3)
        after = event_ids()
        report["event_ids_before"] = sorted(before)
        report["event_ids_after"] = sorted(after)
        report["no_duplicate_event_open"] = before == after
        with db.connect() as c:
            report["inspection_job_rows"] = c.execute(
                select(func.count()).select_from(jobs).where(jobs.c.id == envelope.message_id)
            ).scalar_one()
            report["duplicate_audit_count"] = sum(
                a.get("reason") == "duplicate_delivery"
                and a.get("message_id") == envelope.message_id
                for a in c.execute(
                    select(records.c.body).where(records.c.kind == "audit")
                ).scalars()
            )
        report["browser"] = run(OUT / "browser", url="http://localhost:19080")
        report["status"] = (
            "passed"
            if report["no_duplicate_event_open"]
            and report["inspection_job_rows"] == 1
            and report["duplicate_audit_count"] >= 2
            and all(report["browser"]["checks"].values())
            else "partial"
        )
    finally:
        subprocess.run(
            ["docker", "stop", "twinguard-phase7-corrected-fast-worker-1"],
            check=True,
            capture_output=True,
        )
        report["finished_at"] = now().isoformat()
        (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
