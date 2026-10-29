"""Explicit hash-verified evidence migration; only resource-guard source drift allowed."""

from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timezone
from twinguard.evaluation.campaigns import digest, atomic_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/outputs/phase7-V3-heldout-planners"
DESTINATION = Path("/mnt/d/TwinGuard/phase7-V3-heldout-planners")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    if DESTINATION.exists():
        raise ValueError("New migration destination required")
    before = json.loads((SOURCE / "campaign.json").read_text())
    hashes = before["configuration"]["source_hashes"]
    changes = {
        name: {"old": checksum, "new": sha(ROOT / name)}
        for name, checksum in hashes.items()
        if sha(ROOT / name) != checksum
    }
    if set(changes) != {"src/twinguard/evaluation/campaigns.py"}:
        raise ValueError(
            "Migration permits ONLY destination-aware resource guard change: " + str(changes.keys())
        )
    shutil.copytree(SOURCE, DESTINATION)
    entries = []
    for p in sorted(SOURCE.rglob("*")):
        if p.is_file():
            relative = p.relative_to(SOURCE)
            original = sha(p)
            copied = sha(DESTINATION / relative)
            if original != copied:
                raise ValueError("Migration integrity mismatch " + str(relative))
            entries.append({"path": str(relative), "sha256": original, "bytes": p.stat().st_size})
    atomic_json(DESTINATION / "campaign.before-storage-migration.json", before)
    state = json.loads((DESTINATION / "campaign.json").read_text())
    state.setdefault("infrastructure_migrations", []).append(
        {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "source": str(SOURCE),
            "destination": str(DESTINATION),
            "prior_configuration_hash": state["configuration_hash"],
            "source_changes": changes,
            "rationale": "User-provided D drive; unchanged scientific candidates, cases, seeds, sensing and downstream processing",
        }
    )
    for name, change in changes.items():
        state["configuration"]["source_hashes"][name] = change["new"]
    state["configuration_hash"] = digest(state["configuration"])
    atomic_json(DESTINATION / "campaign.json", state)
    atomic_json(
        ROOT / "docs/phase7/external_evidence_migration.json",
        {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "source": str(SOURCE),
            "destination": str(DESTINATION),
            "files": entries,
            "source_changes": changes,
            "completed_cases_before": len(before["completed"]),
            "new_configuration_hash": state["configuration_hash"],
            "prior_configuration_hash": before["configuration_hash"],
        },
    )
    retained = SOURCE.with_name(SOURCE.name + ".pre-external-migration")
    SOURCE.rename(retained)
    SOURCE.symlink_to(DESTINATION, target_is_directory=True)
    print("Verified", len(entries), "files; original retained at", retained)


if __name__ == "__main__":
    main()
