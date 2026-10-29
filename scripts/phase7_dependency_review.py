"""Query the public OSV primary advisory API for actually installed locked dependencies."""

from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import version
import json
import re
import httpx

root = Path(__file__).resolve().parents[1]
out = root / "experiments/outputs/phase7-V6-dependency-review"
out.mkdir(parents=True, exist_ok=False)
packages = {}
for file in root.glob("requirements*.lock"):
    for line in file.read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^ ;]+)", line)
        if m:
            name = m.group(1)
            try:
                packages[name] = version(name)
            except Exception:
                pass
report = {
    "at_utc": datetime.now(timezone.utc).isoformat(),
    "source": "https://api.osv.dev/v1/querybatch",
    "scope": "Installed Python packages appearing in repository lockfiles; not an image, OS or npm scan",
    "packages": packages,
}
try:
    with httpx.Client(timeout=45) as client:
        names = sorted(packages)
        response = client.post(
            report["source"],
            json={
                "queries": [
                    {"package": {"name": name, "ecosystem": "PyPI"}, "version": packages[name]}
                    for name in names
                ]
            },
        )
        response.raise_for_status()
        results = response.json()["results"]
        report["results"] = {name: r for name, r in zip(names, results)}
        report["affected_packages"] = [
            name for name, r in report["results"].items() if r.get("vulns")
        ]
        report["status"] = "executed"
except Exception as exc:
    report["status"] = "pending_external_advisory_access"
    report["error"] = type(exc).__name__ + ": " + str(exc)[:300]
(out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(report["status"], len(packages), "packages")
