"""Resource-bounded, checkpointed scientific execution; never a production planner input."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def resource_preflight(reserve_bytes=0, minimum_linux_gib=10, minimum_host_gib=8):
    measurements = {}
    destination = os.environ.get("TWINGUARD_CAMPAIGN_STORAGE")
    if destination:
        target = Path(destination).resolve(strict=True)
        checks = [
            ("linux", Path("/"), minimum_linux_gib, 0),
            ("source_host", Path("/mnt/c"), 1, 0),
            ("destination", target, minimum_host_gib, reserve_bytes),
        ]
    else:
        checks = [
            ("linux", Path("/"), minimum_linux_gib, reserve_bytes),
            ("host", Path("/mnt/c"), minimum_host_gib, reserve_bytes),
        ]
    for name, path, limit, reserved in checks:
        if not path.exists():
            continue
        free = shutil.disk_usage(path).free
        measurements[name] = {
            "path": str(path),
            "free_bytes": free,
            "minimum_free_gib": limit,
            "reserved_bytes": reserved,
        }
        if free - reserved < limit * 1024**3:
            raise RuntimeError(
                f"{name} storage preflight failed: {free / 1024**3:.2f} GiB free, reserve {reserved / 1024**3:.2f} GiB, floor {limit} GiB; no historical data removed"
            )
    return measurements


class Campaign:
    def __init__(self, path, configuration, resume=False, reserve_bytes=0):
        self.path = Path(path)
        self.configuration = configuration
        self.preflight = resource_preflight(reserve_bytes)
        existing = self.path / "campaign.json"
        if existing.exists():
            if not resume:
                raise ValueError("Choose a new campaign directory or explicit resume")
            self.state = json.loads(existing.read_text())
            if self.state["configuration_hash"] != digest(configuration):
                raise ValueError("Resume configuration mismatch")
            for ident, checksum in self.state["completed"].items():
                if (
                    hashlib.sha256((self.path / "cases" / f"{ident}.json").read_bytes()).hexdigest()
                    != checksum
                ):
                    raise ValueError("Checkpoint integrity failure")
        else:
            if self.path.exists() and any(self.path.iterdir()):
                raise ValueError("Nonempty unrecognized campaign")
            self.path.mkdir(parents=True, exist_ok=True)
            self.state = {
                "configuration": configuration,
                "configuration_hash": digest(configuration),
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "running",
                "completed": {},
                "preflight": self.preflight,
            }
        if resume:
            self.state.setdefault("resume_history", []).append(
                {
                    "prior_status": self.state["status"],
                    "prior_error": self.state.pop("error", None),
                    "resumed_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
        self.state["status"] = "running"
        self.flush()

    def flush(self):
        atomic_json(self.path / "campaign.json", self.state)

    def commit(self, ident, value):
        resource_preflight()
        if len(self.state["completed"]) % 10 == 0:
            used = sum(p.stat().st_size for p in self.path.rglob("*") if p.is_file())
            self.state["observed_campaign_bytes"] = used
            if used > self.configuration.get("maximum_new_campaign_bytes", 6 * 1024**3):
                raise RuntimeError(
                    "Campaign artifact budget exceeded; outputs preserved as incomplete"
                )
        path = self.path / "cases" / f"{ident}.json"
        if ident in self.state["completed"]:
            raise ValueError("Completed case immutable")
        atomic_json(path, value)
        self.state["completed"][ident] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.flush()

    def finish(self, expected):
        if len(self.state["completed"]) != expected:
            raise ValueError("Cannot complete an incomplete campaign")
        self.state.update(status="completed", ended_at_utc=datetime.now(timezone.utc).isoformat())
        self.flush()

    def fail(self, error):
        self.state.update(
            status="incomplete",
            error=str(error),
            ended_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        self.flush()
