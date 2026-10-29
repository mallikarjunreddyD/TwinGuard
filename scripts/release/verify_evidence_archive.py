"""Independently verify archive paths, objects, counts, hashes and secret exclusion."""

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from build_evidence_archive import sha, sensitive


def safe(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or ".." in p.parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe archive path")
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()) or any(
        part.is_symlink() for part in [target, *target.parents] if part != root.parent
    ):
        raise ValueError("Symlink escape")
    return target


def verify(root, manifest_name="manifest.json"):
    root = root.resolve()
    manifest = json.loads(safe(root, manifest_name).read_text())
    errors, seen, objects = [], set(), set()
    count = total = 0
    lookup = {}
    if manifest["schema_version"] != "1.0.0":
        raise ValueError("Unsupported manifest schema")
    inventory = safe(root, manifest["inventory"])
    if sha(inventory) != manifest["inventory_sha256"]:
        errors.append("inventory checksum mismatch")
    for line in inventory.read_text().splitlines():
        row = json.loads(line)
        safe(root, row["path"])
        identity = (row["source_root"], row["path"])
        if identity in seen:
            errors.append("duplicate logical path: " + str(identity))
        seen.add(identity)
        lookup[identity] = row
        p = safe(root, row["object_path"])
        if sensitive(Path(row["path"])):
            errors.append("sensitive file included")
        if not p.is_file() or p.stat().st_size != row["bytes"]:
            errors.append("missing/size mismatch: " + str(identity))
        elif str(p) not in objects:
            if sha(p) != row["sha256"]:
                errors.append("hash mismatch: " + str(identity))
            if p.stat().st_size < 8 * 1024**2:
                content = p.read_bytes()
                if (b"-----BEGIN " in content and b"PRIVATE KEY-----" in content) or re.search(
                    rb'(?i)"(?:password|access_token|api_key)"\s*:\s*"[^" ]{4,}"', content
                ):
                    errors.append("credential-like content in object: " + row["object_path"])
            objects.add(str(p))
        count += 1
        total += row["bytes"]
    for reference in manifest.get("required_references", []):
        if (reference["root"], reference["path"]) not in lookup:
            errors.append("missing required reference: " + str(reference))
    freeze_key = ("reports", "phase7/CANDIDATE_FREEZE.json")
    if manifest.get("require_scientific_freeze", False):
        if freeze_key not in lookup:
            errors.append("missing scientific freeze metadata")
        else:
            frozen = json.loads(safe(root, lookup[freeze_key]["object_path"]).read_text())
            for name, expected in frozen["sources"].items():
                if name.startswith(
                    (
                        "src/twinguard/analytics/",
                        "src/twinguard/fusion/",
                        "src/twinguard/sensing/",
                        "src/twinguard/inspection/",
                        "configs/",
                    )
                ):
                    prefix, path = name.split("/", 1)
                    key = ("source" if prefix == "src" else "configs", path)
                    if key not in lookup or lookup[key]["sha256"] != expected:
                        errors.append("frozen scientific mismatch: " + name)
    if (count, total) != (manifest["file_count"], manifest["total_bytes"]):
        errors.append("manifest count/bytes mismatch")
    return dict(
        status="PASS"
        if not errors and not manifest["missing_expected_roots"]
        else "PARTIAL"
        if not errors
        else "FAIL",
        files=count,
        bytes=total,
        unique_objects_verified=len(objects),
        errors=errors,
        missing_expected_roots=manifest["missing_expected_roots"],
        manifest_sha256=sha(safe(root, manifest_name)),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive", type=Path)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--manifest", default="manifest.json")
    a = p.parse_args()
    result = verify(a.archive, a.manifest)
    a.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
