"""Archive integrity checks use isolated fixtures, never scientific originals."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/release"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "archive_verifier", SCRIPTS / "verify_evidence_archive.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(root, content=b"preserved observation", path="sample.json"):
    digest = hashlib.sha256(content).hexdigest()
    obj = root / "public_research/objects" / digest
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(content)
    row = dict(
        source_root="outputs",
        path=path,
        object_path=str(obj.relative_to(root)),
        bytes=len(content),
        sha256=digest,
    )
    inventory = root / "files.jsonl"
    inventory.write_text(json.dumps(row) + "\n")
    (root / "manifest.json").write_text(
        json.dumps(
            dict(
                schema_version="1.0.0",
                inventory="files.jsonl",
                inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(),
                file_count=1,
                total_bytes=len(content),
                missing_expected_roots=[],
            )
        )
    )
    return obj


def test_valid_archive(tmp_path):
    fixture(tmp_path)
    assert module.verify(tmp_path)["status"] == "PASS"


def test_corrupted_copy(tmp_path):
    obj = fixture(tmp_path)
    obj.write_bytes(b"X" * obj.stat().st_size)
    assert module.verify(tmp_path)["status"] == "FAIL"


def test_missing_object(tmp_path):
    fixture(tmp_path).unlink()
    assert module.verify(tmp_path)["status"] == "FAIL"


@pytest.mark.parametrize("path", ["../escape", "/absolute", "C:/outside"])
def test_unsafe_paths(tmp_path, path):
    fixture(tmp_path, path=path)
    with pytest.raises(ValueError, match="Unsafe"):
        module.verify(tmp_path)


def test_symlink_escape(tmp_path):
    obj = fixture(tmp_path)
    other = tmp_path.parent / (tmp_path.name + "-outside")
    other.write_bytes(obj.read_bytes())
    obj.unlink()
    obj.symlink_to(other)
    with pytest.raises(ValueError, match="Symlink"):
        module.verify(tmp_path)


def test_private_identity_rejected(tmp_path):
    fixture(tmp_path, content=b"-----BEGIN RSA PRIVATE KEY----- secret")
    assert module.verify(tmp_path)["status"] == "FAIL"


def test_duplicate_logical_paths(tmp_path):
    fixture(tmp_path)
    inventory = tmp_path / "files.jsonl"
    inventory.write_text(inventory.read_text() * 2)
    manifest = tmp_path / "manifest.json"
    data = json.loads(manifest.read_text())
    data["inventory_sha256"] = hashlib.sha256(inventory.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    assert any("duplicate logical path" in error for error in module.verify(tmp_path)["errors"])


def test_required_freeze_missing(tmp_path):
    fixture(tmp_path)
    manifest = tmp_path / "manifest.json"
    data = json.loads(manifest.read_text())
    data["require_scientific_freeze"] = True
    manifest.write_text(json.dumps(data))
    assert module.verify(tmp_path)["status"] == "FAIL"


def test_builder_deduplicates_excludes_secrets_and_refuses_overwrite(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "observation.json").write_text('{"value": 42}')
    (source / "same.json").write_text('{"value": 42}')
    (source / "identity.key").write_text("private identity must be excluded")
    archive = tmp_path / "archive"
    command = [
        sys.executable,
        str(SCRIPTS / "build_evidence_archive.py"),
        "--destination",
        str(archive),
        "--revision",
        "0" * 40,
        "--root",
        "sample=" + str(source),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((archive / "manifest.json").read_text())
    assert manifest["file_count"] == 2
    assert manifest["unique_objects"] == 1
    assert len(manifest["excluded"]) == 1
    assert module.verify(archive)["status"] == "PASS"
    before = (archive / "manifest.json").read_bytes()
    result = subprocess.run(command + ["--resume"], capture_output=True, text=True)
    assert result.returncode != 0
    assert (archive / "manifest.json").read_bytes() == before
