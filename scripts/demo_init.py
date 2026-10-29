"""One-time local demo provisioning; never exposed through the operational API."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def atomic(path, body, mode=0o600):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).chmod(mode)
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profile", choices=["simulation", "site-review"], default="simulation")
    a = p.parse_args()
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/edge_init.py"), "--profile", a.profile], check=True
    )
    directory = ROOT / ".edge"
    values = json.loads((directory / "secrets.json").read_text())
    for name in ("simulation-controller", "simulation-database"):
        values.setdefault(name, secrets.token_urlsafe(32))
    atomic(directory / "secrets.json", json.dumps(values))
    users = json.loads((directory / "users.json").read_text())
    users[hashlib.sha256(values["simulation-controller"].encode()).hexdigest()] = dict(
        actor="simulation-controller", role="operator"
    )
    atomic(directory / "users.json", json.dumps(users), 0o644)
    sql = directory / "database-init.sql"
    sql.write_text(
        sql.read_text()
        + "CREATE ROLE tg_simulation LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '"
        + values["simulation-database"]
        + "';\nGRANT CONNECT ON DATABASE twinguard TO tg_simulation;\nGRANT USAGE ON SCHEMA public TO tg_simulation;\n"
    )
    atomic(
        directory / "controller.env",
        "TWINGUARD_DEMO_DB=postgresql+psycopg://tg_simulation:"
        + values["simulation-database"]
        + "@database/twinguard\n",
    )
    atomic(
        directory / "controller.json",
        json.dumps(
            {
                "demo-iot": values["demo-iot"],
                "demo-uav": values["demo-uav"],
                "operator": values["simulation-controller"],
            }
        ),
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "-v",
            str(directory) + ":/secrets",
            "--entrypoint",
            "sh",
            "python:3.12-slim",
            "-c",
            "chown 10001:10001 /secrets/controller.json; chmod 400 /secrets/controller.json",
        ],
        check=True,
    )
    print(
        "Local demo credentials provisioned. No secrets printed. Use a fresh isolated Compose project; existing databases require authorized role/migration provisioning."
    )


if __name__ == "__main__":
    main()
