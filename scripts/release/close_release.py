"""Close/publish release metadata only after independent whole-archive verification."""

import argparse
import datetime
import json
from pathlib import Path
import subprocess
from build_evidence_archive import sha
from verify_evidence_archive import verify


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive", type=Path)
    p.add_argument("--source-git", required=True)
    p.add_argument("--publish", action="store_true")
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    doc = root / "docs/release"

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    if (
        git("branch", "--show-current") != "phase-7-release-finalization"
        or git("rev-parse", "HEAD") != a.source_git
    ):
        raise SystemExit("Release branch/source changed; review before closing")
    checks = json.loads((doc / "RELEASE_CHECKS.json").read_text())
    if checks["software_status"] != "PASS":
        raise SystemExit("Software checks are not PASS")
    archive = a.archive.resolve()
    if not (archive / "manifest.release.json").exists():
        subprocess.run(
            [
                str(root / ".venv/bin/python"),
                str(root / "scripts/release/finalize_evidence_archive.py"),
                str(archive),
                "--release-source-git",
                a.source_git,
            ],
            check=True,
        )
    result = verify(archive, "manifest.release.json")
    previous = json.loads((doc / "ARCHIVE_VERIFICATION.json").read_text())
    previous.update(
        status=result["status"],
        full_archive_status=result["status"],
        full_archive_verification=result,
        checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    (doc / "ARCHIVE_VERIFICATION.json").write_text(json.dumps(previous, indent=2) + "\n")
    if result["status"] != "PASS":
        raise SystemExit("Archive verification did not PASS; no release push")
    descriptor = json.loads((archive / "manifest.release.json").read_text())
    pointer = json.loads((doc / "REPRODUCIBILITY_MANIFEST.json").read_text())
    pointer.update(
        release_status="PASS",
        final_release_source_git=a.source_git,
        archive_integrity_status="PASS",
        full_manifest_relative_path="manifest.release.json",
        detailed_file_inventory_relative_path=descriptor["inventory"],
        manifest_sha256=sha(archive / "manifest.release.json"),
        inventory_sha256=descriptor["inventory_sha256"],
        file_count=result["files"],
        total_bytes=result["bytes"],
        unique_objects_verified=result["unique_objects_verified"],
        excluded_files=len(descriptor["excluded"]),
        missing_or_incomplete=[],
        final_packaging_revision_note="The following metadata-only Git commit identifies final packaging; this SHA identifies the checked source revision.",
    )
    (doc / "REPRODUCIBILITY_MANIFEST.json").write_text(json.dumps(pointer, indent=2) + "\n")
    checks.update(
        final_source_revision=a.source_git,
        final_revision=a.source_git,
        final_revision_scope="Checked release source; the following commit packages verification metadata",
        archive_status="PASS",
    )
    (doc / "RELEASE_CHECKS.json").write_text(json.dumps(checks, indent=2) + "\n")
    inventory = doc / "ARCHIVE_INVENTORY.md"
    inventory.write_text(
        inventory.read_text()
        + f"\n\n## Independently verified closeout\n\nPASS: {result['files']} logical files, {result['bytes']} bytes, {result['unique_objects_verified']} unique object paths independently verified. Excluded sensitive identities/configurations: {len(descriptor['excluded'])}. Detailed exclusions and original-root mappings remain in the external descriptor; originals retained. Original source counts differ from logical archived counts because of declared exclusions and additional experiment definitions. Git alone does not contain raw data.\n"
    )
    readiness = root / "docs/RELEASE_READINESS.md"
    readiness.write_text(
        "# Final release decision\n\n**PASS — software checks and whole-archive integrity verified. Research/industrial readiness remains conditional.**\n\nThe following historical construction snapshot is retained for audit; its pending statements are superseded by `release/ARCHIVE_VERIFICATION.json` and the verified manifest. No physical TRL 6 or safety certification is claimed.\n\n"
        + readiness.read_text()
    )
    subprocess.run(["git", "diff", "--check"], cwd=root, check=True)
    paths = [
        "docs/RELEASE_READINESS.md",
        "docs/release/ARCHIVE_INVENTORY.md",
        "docs/release/ARCHIVE_VERIFICATION.json",
        "docs/release/REPRODUCIBILITY_MANIFEST.json",
        "docs/release/RELEASE_CHECKS.json",
    ]
    subprocess.run(["git", "add", *paths], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "Verify complete release archive and close reproducibility packaging",
        ],
        cwd=root,
        check=True,
    )
    if a.publish:
        subprocess.run(
            ["git", "push", "-u", "origin", "phase-7-release-finalization"], cwd=root, check=True
        )
    print("Release archive PASS; final metadata commit", git("rev-parse", "HEAD"), flush=True)


if __name__ == "__main__":
    main()
