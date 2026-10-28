"""Generate local secrets (never committed), broker ACLs and source registry."""

import argparse
import hashlib
import json
import secrets
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--profile", choices=["simulation", "site-review"], default="simulation")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
out = root / ".edge"
out.mkdir(exist_ok=True, mode=0o700)
secrets_path = out / "secrets.json"
if not secrets_path.exists():
    secrets_path.write_text(
        json.dumps(
            {
                k: secrets.token_urlsafe(32)
                for k in [
                    "database",
                    "ingestion",
                    "demo-iot",
                    "demo-uav",
                    "viewer",
                    "operator",
                    "admin",
                ]
            }
        )
    )
    secrets_path.chmod(0o600)
s = json.loads(secrets_path.read_text())
if "database_admin" not in s:
    s["database_admin"] = secrets.token_urlsafe(32)
    secrets_path.write_text(json.dumps(s))
(out / "database-init.sql").write_text(
    "CREATE ROLE twinguard LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '"
    + s["database"]
    + "';\nGRANT CONNECT ON DATABASE twinguard TO twinguard;\nGRANT USAGE, CREATE ON SCHEMA public TO twinguard;\n"
)
(out / "runtime.env").write_text(
    "\n".join(
        [
            "TWINGUARD_DB=postgresql+psycopg://twinguard:" + s["database"] + "@database/twinguard",
            "POSTGRES_PASSWORD=" + s["database_admin"],
            "TWINGUARD_INGEST_PASSWORD=" + s["ingestion"],
            "TWINGUARD_PROFILE=" + args.profile,
            "TWINGUARD_MQTT_HOST=broker",
            "TWINGUARD_ARTIFACTS=/data/artifacts",
            "TWINGUARD_ROOT=/app",
            "TWINGUARD_PORT=18780",
        ]
    )
    + "\n"
)
(out / "runtime.env").chmod(0o600)
(out / "users.json").write_text(
    json.dumps(
        {
            hashlib.sha256(s[role].encode()).hexdigest(): {"actor": role + "-local", "role": role}
            for role in ["viewer", "operator", "admin"]
        }
    )
)
(out / "credentials.txt").write_text(
    "\n".join(k + ":" + s[k] for k in ["ingestion", "demo-iot", "demo-uav"]) + "\n"
)
subprocess.run(
    [
        "docker",
        "run",
        "--rm",
        "-v",
        str(out) + ":/secrets",
        "eclipse-mosquitto:2",
        "sh",
        "-c",
        "cp /secrets/credentials.txt /secrets/passwords; mosquitto_passwd -U /secrets/passwords",
    ],
    check=True,
)
(out / "credentials.txt").unlink()
(out / "acl").write_text(
    "user ingestion\ntopic read twinguard/v1/plant-01/+/+/+\n"
    + "".join(
        f"user {name}\ntopic write twinguard/v1/plant-01/{channel}/{name}/{suffix}\n"
        for name, channel, suffix in [
            ("demo-iot", "iot", "observations"),
            ("demo-uav", "inspection", "manifests"),
        ]
    )
)
(out / "mosquitto.conf").write_text(
    "listener 1883\nallow_anonymous false\npassword_file /mosquitto/config/passwords\nacl_file /mosquitto/config/acl\npersistence true\npersistence_location /mosquitto/data/\nmax_packet_size 131072\nmax_queued_messages 10000\nlog_type warning\n"
)
installation = json.loads((root / "configs/sensing/L1.yaml").read_text())
sensors = {
    v["sensor_id"]: {
        "asset_id": v["asset_id"],
        "measurement_type": {
            "process_temperature": "temperature",
            "surface_temperature": "temperature",
            "pressure": "pressure",
            "load": "operating_load",
            "vibration": "vibration_rms",
        }[v["source"]],
        "unit": {
            "process_temperature": "degC",
            "surface_temperature": "degC",
            "pressure": "Pa",
            "load": "1",
            "vibration": "m/s2",
        }[v["source"]],
    }
    for v in installation["iot"]
}
registry = [
    {
        "source_id": name,
        "transport_identity": identity,
        "sensors": sensors if name != "demo-uav" else {},
        "clock_quality": "synchronized",
        "clock_basis": "controlled_simulation_replay",
        "calibration_status": "assumed_simulation",
        "calibration_reference": "assumed-v1",
        "allow_inspections": name == "demo-uav",
        "capture_sensors": {"lidar-01": ["BW-01"], "thermal-01": ["BW-01"]}
        if name == "demo-uav"
        else {},
    }
    for name, identity in [
        ("demo-iot", "demo-iot"),
        ("demo-uav", "demo-uav"),
        ("opcua-demo", "opcua-adapter"),
    ]
]
(root / "configs/edge/simulation-sources.json").write_text(json.dumps(registry, indent=2) + "\n")
site = [
    {
        **r,
        "clock_quality": "unknown",
        "clock_basis": "unverified",
        "calibration_status": "unknown",
        "calibration_reference": None,
        "allow_inspections": False,
    }
    for r in registry
]
(root / "configs/edge/site-review-sources.json").write_text(json.dumps(site, indent=2) + "\n")
print(
    "Local secrets generated under .edge (ignored). Tokens are in .edge/secrets.json; never commit them."
)
