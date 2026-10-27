"""Regenerate version pins from the validated environment; run from repository root."""

from importlib.metadata import distribution, distributions
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def closure(names):
    found = set()
    pending = list(names)
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found:
            continue
        found.add(name)
        for raw in distribution(name).requires or []:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return found


runtime = set()
pending = ["pydantic", "numpy", "PyYAML", "fastapi", "uvicorn", "trimesh"]
while pending:
    name = canonicalize_name(pending.pop())
    if name in runtime:
        continue
    runtime.add(name)
    dist = distribution(name)
    for raw in dist.requires or []:
        requirement = Requirement(raw)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            pending.append(requirement.name)
installed = {canonicalize_name(d.metadata["Name"]): d.version for d in distributions()}
header = "# Validated Python 3.12 Linux environment; regenerate with scripts/lock_dependencies.py\n"
for filename, names in [
    ("requirements-runtime.lock", runtime),
    ("requirements-sensing.lock", runtime | closure(["open3d"])),
    ("requirements-dev.lock", set(installed) - {"twinguard", "pip", "setuptools"}),
]:
    Path(filename).write_text(
        header + "".join(f"{name}=={installed[name]}\n" for name in sorted(names))
    )
