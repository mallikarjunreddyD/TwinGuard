"""Actual PostgreSQL snapshot/dump/restore and content-addressed artifact verification.

Only the new Phase 7 stack is read. Restore targets a new database, never the source.
Snapshot counts and hashes bind the dump to a consistent live source transaction.
"""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import time
import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "twinguard-phase7-database-1"


def cmd(args, **kw):
    return subprocess.run(args, check=True, capture_output=True, **kw)


def fingerprint_tables(connection):
    tables = (
        connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        )
        .scalars()
        .all()
    )
    result = {}
    for table in tables:
        if not table.replace("_", "").isalnum():
            raise ValueError("Unexpected identifier")
        started = time.perf_counter()
        # Stable canonical JSON row checksums; stream rows rather than concatenate raw payloads.
        checks = connection.execution_options(stream_results=True).execute(
            text(f'SELECT md5(row_to_json(t)::text) AS checksum FROM "{table}" t ORDER BY checksum')
        )
        digest = hashlib.sha256()
        count = 0
        for row in checks:
            digest.update(row[0].encode())
            count += 1
        result[table] = {
            "rows": count,
            "canonical_rows_sha256": digest.hexdigest(),
            "scan_s": time.perf_counter() - started,
        }
    return result


def main(output, restore_name="phase7_restore_validation", archive_root=None):
    if (
        not restore_name.startswith("phase7_restore_")
        or not restore_name.replace("_", "").isalnum()
    ):
        raise ValueError("New Phase7 restore database identifier required")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    url = "postgresql+psycopg://twinguard:" + secrets["database"] + "@127.0.0.1:18982/"
    db = create_engine(url + "twinguard")
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Actual live PostgreSQL snapshot backup and isolated restore; no 90-day endurance claim",
        "source_container": CONTAINER,
        "restored_database": restore_name,
        "git": cmd(["git", "rev-parse", "HEAD"], text=True).stdout.strip(),
    }
    with db.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            snapshot = connection.execute(text("SELECT pg_export_snapshot()")).scalar_one()
            report["source_tables"] = fingerprint_tables(connection)
            report["database_bytes"] = connection.execute(
                text("SELECT pg_database_size(current_database())")
            ).scalar_one()
            report["relations"] = [
                dict(r)
                for r in connection.execute(
                    text(
                        "SELECT relname,pg_total_relation_size(relid) AS total_bytes,pg_relation_size(relid) AS heap_bytes,pg_indexes_size(relid) AS index_bytes FROM pg_stat_user_tables ORDER BY relname"
                    )
                ).mappings()
            ]
            report["record_kinds"] = [
                dict(r)
                for r in connection.execute(
                    text(
                        "SELECT kind,count(*) AS rows,sum(octet_length(body::text)) AS json_bytes FROM records GROUP BY kind ORDER BY kind"
                    )
                ).mappings()
            ]
            started = time.perf_counter()
            with (output / "database.dump").open("wb") as f:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        CONTAINER,
                        "pg_dump",
                        "-U",
                        "twinguard",
                        "-d",
                        "twinguard",
                        "--format=custom",
                        "--snapshot",
                        snapshot,
                    ],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    check=True,
                )
            report["dump_s"] = time.perf_counter() - started
            report["dump_bytes"] = (output / "database.dump").stat().st_size
            report["dump_sha256"] = hashlib.sha256(
                (output / "database.dump").read_bytes()
            ).hexdigest()
            artifacts = [
                r[0]
                for r in connection.execute(text("SELECT body FROM records WHERE kind='artifact'"))
            ]
    # A new fixed name makes repeat execution fail safely rather than replace prior restores.
    cmd(
        [
            "docker",
            "exec",
            CONTAINER,
            "createdb",
            "-U",
            "tg_admin",
            "-O",
            "twinguard",
            restore_name,
        ]
    )
    started = time.perf_counter()
    with (output / "database.dump").open("rb") as f:
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                CONTAINER,
                "pg_restore",
                "-U",
                "twinguard",
                "-d",
                restore_name,
                "--no-owner",
                "--exit-on-error",
            ],
            stdin=f,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    report["restore_s"] = time.perf_counter() - started
    restored = create_engine(url + restore_name)
    with restored.connect() as c:
        report["restored_tables"] = fingerprint_tables(c)
    report["row_integrity_equal"] = all(
        {k: v for k, v in row.items() if k != "scan_s"}
        == {k: v for k, v in report["restored_tables"][name].items() if k != "scan_s"}
        for name, row in report["source_tables"].items()
    )
    report["artifact_metadata_count"] = len(artifacts)
    # Copy the actual CAS directory into a new backup archive and extract it independently.
    with (output / "artifacts.tar").open("wb") as f:
        subprocess.run(
            [
                "docker",
                "exec",
                "twinguard-phase7-api-1",
                "tar",
                "-C",
                "/data",
                "-cf",
                "-",
                "artifacts",
            ],
            stdout=f,
            stderr=subprocess.PIPE,
            check=True,
        )
    target = output / "restored-artifacts"
    target.mkdir()
    import tarfile

    with tarfile.open(output / "artifacts.tar") as archive:
        archive.extractall(target, filter="data")
    files = []
    for path in sorted(target.rglob("*")):
        if path.is_file():
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append(
                {
                    "path": str(path.relative_to(target)),
                    "bytes": path.stat().st_size,
                    "sha256": checksum,
                    "content_address_matches": path.name.split(".")[0] == checksum,
                }
            )
    report["restored_artifact_files"] = files
    report["artifacts_integrity_equal"] = all(f["content_address_matches"] for f in files)
    report["artifact_archive_sha256"] = hashlib.sha256(
        (output / "artifacts.tar").read_bytes()
    ).hexdigest()
    headers = {"Authorization": "Bearer " + secrets["viewer"]}
    query = []
    with httpx.Client(timeout=30) as client:
        for endpoint in ("assets", "events", "inspection-plans", "platform/health"):
            times = []
            statuses = []
            for _ in range(10):
                started = time.perf_counter()
                r = client.get("http://localhost:18980/api/v1/" + endpoint, headers=headers)
                times.append(time.perf_counter() - started)
                statuses.append(r.status_code)
            query.append({"endpoint": endpoint, "latency_s": times, "statuses": statuses})
    report["queries"] = query
    if archive_root:
        import shutil
        from twinguard.edge.archive import recover_raw

        archive_destination = output / "restored-raw-archives"
        shutil.copytree(archive_root, archive_destination)
        recovered = []
        with restored.connect() as c:
            ids = (
                c.execute(
                    text(
                        "SELECT id FROM records WHERE kind='archive' AND body->>'format'='gzip-jsonl-v1' ORDER BY id"
                    )
                )
                .scalars()
                .all()
            )
            for ident in ids:
                row = recover_raw(c, ident, archive_destination)
                recovered.append(row["id"])
        report["restored_raw_archive_rows"] = len(recovered)
        report["raw_archive_integrity_equal"] = len(recovered) == len(ids)
        report["raw_archive_files"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in archive_destination.iterdir()
            if p.is_file()
        }

    report["status"] = (
        "passed"
        if report["row_integrity_equal"] and report["artifacts_integrity_equal"]
        else "failed"
    )
    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    (output / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(report["status"], report["database_bytes"], report["dump_bytes"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--restore-name", default="phase7_restore_validation")
    p.add_argument("--archive-root", type=Path)
    a = p.parse_args()
    main(a.output, a.restore_name, a.archive_root)
