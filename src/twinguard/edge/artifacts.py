"""Immutable, bounded public-only bundles; no caller-supplied server paths."""

import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
from twinguard.core.observations import load_public_observations, load_capture_arrays
from twinguard.core.contracts import InspectionCapture


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, digest):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("invalid_object_key")
        return self.root / digest

    def upload(self, data):
        if len(data) > 64 * 1024 * 1024:
            raise ValueError("artifact_size_limit")
        digest = hashlib.sha256(data).hexdigest()
        path = self.path(digest)
        if not path.exists():
            fd, temporary = tempfile.mkstemp(dir=self.root)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
            finally:
                os.unlink(temporary)
        self.verify_bundle(digest)
        return digest

    def extract(self, digest, destination):
        data = self.path(digest).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("artifact_checksum_mismatch")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if (
                len(z.infolist()) > 3000
                or sum(i.file_size for i in z.infolist()) > 128 * 1024 * 1024
            ):
                raise ValueError("expanded_artifact_size_limit")
            seen = set()
            for info in z.infolist():
                name = PurePosixPath(info.filename)
                if (
                    info.filename in seen
                    or name.is_absolute()
                    or ".." in name.parts
                    or "\\" in info.filename
                ):
                    raise ValueError("unsafe_artifact_path")
                seen.add(info.filename)
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError("artifact_symlink")
                if str(name) != "manifest.json" and (
                    not name.parts or name.parts[0] != "observations"
                ):
                    raise ValueError("non_public_artifact")
                if name.suffix not in [".json", ".jsonl", ".csv", ".npz", ".npy", ".ply"]:
                    raise ValueError("unexpected_artifact_format")
                target = Path(destination) / str(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
        records = load_public_observations(Path(destination))
        for record in records:
            if isinstance(record, InspectionCapture):
                if record.artifact.sha256 is None:
                    raise ValueError("missing_capture_hash")
                path = Path(destination) / record.artifact.uri
                if hashlib.sha256(path.read_bytes()).hexdigest() != record.artifact.sha256:
                    raise ValueError("capture_hash_mismatch")
                # npz decompression is separately bounded before NumPy loads arrays.
                if path.suffix == ".npz":
                    with zipfile.ZipFile(path) as archive:
                        if sum(i.file_size for i in archive.infolist()) > 64 * 1024 * 1024:
                            raise ValueError("expanded_array_size_limit")
                load_capture_arrays(Path(destination), record)
        return records

    def verify_bundle(self, digest):
        with tempfile.TemporaryDirectory() as temp:
            return self.extract(digest, Path(temp))
