"""Build a resumable content-addressed research archive; never delete sources."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

EXCLUDED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    ".edge",
    "external-phase7",
    "outputs",
    "releases",
    "release",
}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sensitive(path):
    name = path.name.lower()
    return (
        name.startswith(".env")
        or name.endswith((".key", ".pem", ".pfx", ".p12"))
        or name in {"secrets.json", "runtime.env"}
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--root", action="append", required=True, help="portable-id=source-path")
    p.add_argument("--revision", required=True)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    dest = a.destination.resolve()
    if dest.exists() and not a.resume:
        raise SystemExit("Existing destination requires explicit --resume")
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / "manifest.json").exists():
        raise SystemExit(
            "Archive already finalized; run independent verification rather than overwrite"
        )
    if shutil.disk_usage(dest).free < 8 * 1024**3:
        raise SystemExit("Insufficient initial archive headroom")
    roots = dict(value.split("=", 1) for value in a.root)
    records, exclusions, missing = [], [], []
    pool = ThreadPoolExecutor(max_workers=8)
    journal = dest / "inventory.partial.jsonl"
    if journal.exists():
        previous = dest / ("inventory.interrupted-" + str(__import__("time").time_ns()) + ".jsonl")
        journal.rename(previous)
    with journal.open("w") as output:
        for ident, location in roots.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]+", ident):
                raise ValueError("Unsafe root identifier")
            source = Path(location).resolve()
            if not source.exists():
                missing.append(ident)
                continue
            for folder, dirs, files in os.walk(source, followlinks=False):
                dirs[:] = sorted(
                    d for d in dirs if d not in EXCLUDED and not (Path(folder) / d).is_symlink()
                )

                def process_file(name):
                    path = Path(folder) / name
                    relative = path.relative_to(source).as_posix()
                    if path.is_symlink() or sensitive(path):
                        exclusions.append(
                            {
                                "root": ident,
                                "path": relative,
                                "reason": "symlink or sensitive identity/configuration",
                            }
                        )
                        return None
                    if path.stat().st_size < 8 * 1024**2:
                        content = path.read_bytes()
                        if (
                            b"-----BEGIN " in content
                            and b"PRIVATE KEY-----" in content
                            or re.search(
                                rb'(?i)"(?:password|access_token|api_key)"\s*:\s*"[^" ]{4,}"',
                                content,
                            )
                        ):
                            exclusions.append(
                                {
                                    "root": ident,
                                    "path": relative,
                                    "reason": "credential-like content; conservative exclusion",
                                }
                            )
                            return None
                    digest = sha(path)
                    restricted = any(
                        x in relative.lower()
                        for x in (
                            "ground_truth",
                            "ground-truth",
                            "private",
                            "oracle",
                            "truth",
                            "labels",
                        )
                    )
                    kind = "restricted_evaluation" if restricted else "public_research"
                    object_path = Path(kind) / "objects" / digest[:2] / digest
                    target = dest / object_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        if sha(target) != digest:
                            raise ValueError("Existing CAS corruption")
                    else:
                        if shutil.disk_usage(dest).free < max(8 * 1024**3, path.stat().st_size * 2):
                            raise OSError("Archive headroom exhausted; partial journal retained")
                        fd, temp = tempfile.mkstemp(prefix=".partial-", dir=target.parent)
                        os.close(fd)
                        try:
                            shutil.copyfile(path, temp)
                            if sha(Path(temp)) != digest:
                                raise ValueError("Source changed or copy corrupted")
                            try:
                                os.link(temp, target)
                            except FileExistsError:
                                if sha(target) != digest:
                                    raise ValueError("Concurrent CAS corruption")
                        finally:
                            if Path(temp).exists():
                                Path(temp).unlink()
                    experiment = relative.split("/")[0]
                    record = dict(
                        path=relative,
                        source_root=ident,
                        experiment_id=experiment,
                        phase="phase7" if "phase7" in relative.lower() else "historical_or_shared",
                        artifact_type=path.suffix or "extensionless",
                        bytes=path.stat().st_size,
                        sha256=digest,
                        object_path=object_path.as_posix(),
                        source_git=None,
                        packaging_git=a.revision,
                        configuration_hash=None,
                        calibration_model_hash=None,
                        dataset_id=experiment,
                        seeds=None,
                        execution_status="artifact_preserved_not_inferred",
                        run_timestamp=None,
                        source_mtime_utc=datetime.datetime.fromtimestamp(
                            path.stat().st_mtime, datetime.timezone.utc
                        ).isoformat(),
                        evidence_class=kind,
                        related_report=None,
                    )
                    return record

                for record in pool.map(process_file, sorted(files)):
                    if record is None:
                        continue
                    records.append(record)
                    output.write(json.dumps(record) + "\n")
                    output.flush()
                    if len(records) % 10000 == 0:
                        print("Archived", len(records), flush=True)
    pool.shutdown()
    final = dest / "files.jsonl"
    os.replace(journal, final)
    manifest = dict(
        schema_version="1.0.0",
        software_version="0.8.0",
        release_source_git=a.revision,
        scientific_freeze_git="edae1e5",
        created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        original_roots=roots,
        file_count=len(records),
        total_bytes=sum(r["bytes"] for r in records),
        unique_objects=len({r["object_path"] for r in records}),
        inventory="files.jsonl",
        inventory_sha256=sha(final),
        integrity_status="AWAITING_INDEPENDENT_VERIFICATION",
        missing_expected_roots=missing,
        excluded=exclusions,
        provenance_note="Null per-file producer/configuration/seed fields are unknown, not inferred from packaging revision. Original campaign/configuration journals are preserved objects; use them for run provenance.",
    )
    pending_manifest = dest / "manifest.pending.json"
    with pending_manifest.open("x") as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.link(pending_manifest, dest / "manifest.json")
    pending_manifest.unlink()
    print(
        json.dumps({k: v for k, v in manifest.items() if k not in {"excluded", "original_roots"}}),
        flush=True,
    )


if __name__ == "__main__":
    main()
