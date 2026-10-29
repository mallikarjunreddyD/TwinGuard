"""Append an enriched manifest; preserve the original build manifest and inventory."""

import argparse
import json
import re
from pathlib import Path
from build_evidence_archive import sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive", type=Path)
    p.add_argument("--release-source-git", required=True)
    a = p.parse_args()
    root = a.archive.resolve()
    original = json.loads((root / "manifest.json").read_text())
    inventory = root / original["inventory"]
    contexts, references = {}, set()
    for line in inventory.open():
        row = json.loads(line)
        references.add((row["source_root"], row["path"]))
        if Path(row["path"]).name in {"campaign.json", "source_configuration.json"}:
            try:
                data = json.loads((root / row["object_path"]).read_text())
                contexts[(row["source_root"], str(Path(row["path"]).parent))] = data
            except (ValueError, UnicodeError):
                pass
    enriched = root / "files.release.jsonl"
    if enriched.exists():
        raise SystemExit("Enriched manifest already exists; verify it rather than overwrite")
    temp = root / "files.release.partial.jsonl"
    with temp.open("x") as out:
        for line in inventory.open():
            row = json.loads(line)
            row["packaging_git"] = a.release_source_git
            row["source_git"] = None
            name = row["path"].lower()
            row["artifact_role"] = (
                "restricted_evaluation_truth_or_context"
                if row["evidence_class"] == "restricted_evaluation"
                else "prediction"
                if "predict" in name
                else "raw_observation"
                if "observation" in name
                else "derived_result_or_configuration"
            )
            parent = Path(row["path"]).parent
            while True:
                report = str(parent / "report.json")
                if row.get("related_report") is None and (row["source_root"], report) in references:
                    row["related_report"] = dict(source_root=row["source_root"], path=report)
                context = contexts.get((row["source_root"], str(parent)))
                if context:
                    config = context.get("configuration", context)
                    row["configuration_hash"] = context.get("configuration_hash")
                    row["calibration_model_hash"] = config.get(
                        "calibration_hash",
                        config.get("view_model_sha256", config.get("model_hash")),
                    )
                    row["execution_status"] = context.get("status", row["execution_status"])
                    row["seeds"] = config.get(
                        "seeds", config.get("evaluation_seeds", config.get("seed"))
                    )
                    candidate = context.get("source_git", context.get("source_revision"))
                    if isinstance(candidate, str) and re.fullmatch("[0-9a-f]{40}", candidate):
                        row["source_git"] = candidate
                    row["run_timestamp"] = context.get(
                        "created_at_utc", context.get("started_at_utc")
                    )
                    row["provenance_context"] = dict(
                        source_root=row["source_root"], path=str(parent)
                    )
                    break
                if parent == Path("."):
                    break
                parent = parent.parent
            out.write(json.dumps(row) + "\n")
    temp.rename(enriched)
    manifest = dict(original)
    manifest.update(
        inventory=enriched.name,
        inventory_sha256=sha(enriched),
        release_source_git=a.release_source_git,
        original_build_manifest="manifest.json",
        require_scientific_freeze=True,
        required_references=[
            dict(root="reports", path=name)
            for name in (
                "phase7/CANDIDATE_FREEZE.json",
                "phase3_e1_results.json",
                "phase3_e2_results.json",
                "phase4/results.json",
                "phase6/results.json",
                "phase7/heldout_detector_summary.json",
                "phase7/heldout_planner_summary.json",
                "phase7/fresh_chronology_summary.json",
            )
        ],
    )
    manifest["absent_required_references"] = [
        x for x in manifest["required_references"] if (x["root"], x["path"]) not in references
    ]
    manifest["provenance_note"] = (
        "Producer revisions remain null unless explicitly present in a preserved run journal. Packaging revision is distinct. Context provides declared configuration, seed scope and execution status; absence is unknown."
    )
    with (root / "manifest.release.json").open("x") as out:
        out.write(json.dumps(manifest, indent=2) + "\n")
    print("Enriched manifest appended; independent verification still required")


if __name__ == "__main__":
    main()
