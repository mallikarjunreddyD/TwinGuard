"""Static, recursive import boundary audit; complements runtime serialization checks."""

import ast
from importlib.util import resolve_name
from pathlib import Path

RESTRICTED = (
    "twinguard.evaluation",
    "twinguard.plant",
    "twinguard.core.config",
    "twinguard.core.registry",
    "twinguard.sensing",
)


def forbidden_imports(path: Path, module_name: str) -> list[str]:
    tree = ast.parse(path.read_text())
    package = module_name if path.name == "__init__.py" else module_name.rsplit(".", 1)[0]
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            imported.append(base)
            imported.extend(base + "." + alias.name for alias in node.names)
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                imported.append(node.args[0].value)
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                imported.append(node.args[0].value)
    return [
        name
        for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in RESTRICTED)
    ]


def audit_consumers(package_root: Path) -> list[str]:
    violations: list[str] = []
    for folder in ("analytics", "fusion", "inspection", "api"):
        for path in (package_root / folder).rglob("*.py"):
            module = "twinguard." + ".".join(path.relative_to(package_root).with_suffix("").parts)
            module = module.removesuffix(".__init__")
            violations.extend(f"{path}: {name}" for name in forbidden_imports(path, module))
    return violations
