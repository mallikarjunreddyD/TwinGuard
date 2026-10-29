"""Actual lab TLS and signed/encrypted read-only OPC UA checks. Not site commissioning."""

import asyncio
import json
import os
from pathlib import Path
import ssl
import subprocess
import time
import httpx
from twinguard.edge.protocols import mqtt_client, opc_server
from asyncua import Client, ua

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/outputs/phase7-V6-lab-tls-v3"
CERT = ROOT / ".edge/phase7-lab-tls-v3"


def run(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def certificates():
    CERT.mkdir(parents=True, exist_ok=False)
    run(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(CERT / "ca.key"),
        "-out",
        str(CERT / "ca.pem"),
        "-days",
        "2",
        "-subj",
        "/CN=TwinGuard Phase7 LAB ONLY CA",
    )
    for name in ("server", "client", "wrong"):
        run(
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(CERT / (name + "-key.pem")),
            "-out",
            str(CERT / (name + ".csr")),
            "-subj",
            "/CN=localhost",
        )
        ext = CERT / (name + ".ext")
        ext.write_text(
            "subjectAltName=DNS:localhost,IP:127.0.0.1,URI:urn:freeopcua:"
            + ("server" if name == "server" else "client")
            + "\nextendedKeyUsage=serverAuth,clientAuth\nkeyUsage=digitalSignature,keyEncipherment,dataEncipherment\nbasicConstraints=CA:FALSE\n"
        )
        run(
            "openssl",
            "x509",
            "-req",
            "-in",
            str(CERT / (name + ".csr")),
            "-CA",
            str(CERT / "ca.pem"),
            "-CAkey",
            str(CERT / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(CERT / (name + ".pem")),
            "-days",
            "2",
            "-extfile",
            str(ext),
        )
        (CERT / (name + "-key.pem")).chmod(0o600)
    (CERT / "ca.key").chmod(0o600)


async def opc_checks():
    os.environ["TWINGUARD_OPCUA_SERVER_CERTIFICATE"] = str(CERT / "server.pem")
    os.environ["TWINGUARD_OPCUA_SERVER_PRIVATE_KEY"] = str(CERT / "server-key.pem")
    endpoint = "opc.tcp://127.0.0.1:19484/twinguard/"
    task = asyncio.create_task(opc_server(ROOT / "experiments/outputs/e4-public-8200", endpoint))
    await asyncio.sleep(3)
    results = {}
    try:
        client = Client(endpoint)
        await client.set_security_string(
            "Basic256Sha256,SignAndEncrypt,"
            + str(CERT / "client.pem")
            + ","
            + str(CERT / "client-key.pem")
            + ","
            + str(CERT / "server.pem")
        )
        async with client:
            idx = await client.get_namespace_index("urn:twinguard:measured")
            node = client.get_node(ua.NodeId("pressure-01", idx))
            value = await node.read_data_value()
            results["encrypted_read"] = {
                "value_present": value.Value is not None,
                "source_timestamp_present": value.SourceTimestamp is not None,
                "policy": "Basic256Sha256 SignAndEncrypt",
                "server_certificate_pinned": True,
            }
            try:
                await node.write_value(0.0)
                results["write_rejected"] = False
            except ua.UaStatusCodeError as exc:
                results["write_rejected"] = True
                results["write_status"] = str(exc)
        try:
            async with Client(endpoint):
                results["unencrypted_rejected"] = False
        except Exception as exc:
            results["unencrypted_rejected"] = True
            results["unencrypted_error"] = type(exc).__name__
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    certificates()
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    report = {
        "scope": "Fresh two-day self-signed laboratory CA only; no approved site CA, identity commissioning or trusted clock claim",
        "results": {},
    }
    conf = CERT / "mosquitto.conf"
    conf.write_text(
        "user root\nlistener 8883\nallow_anonymous false\npassword_file /passwords\ncafile /certs/ca.pem\ncertfile /certs/server.pem\nkeyfile /certs/server-key.pem\n"
    )
    nginx = CERT / "nginx.conf"
    nginx.write_text(
        "events {}\nhttp { server { listen 127.0.0.1:19443 ssl; ssl_certificate /certs/server.pem; ssl_certificate_key /certs/server-key.pem; location / { proxy_pass http://127.0.0.1:18980; } } }\n"
    )
    containers = []
    try:
        run(
            "docker",
            "run",
            "-d",
            "--name",
            "twinguard-phase7-lab-tls-mqtt",
            "--user",
            "0:0",
            "-p",
            "127.0.0.1:19483:8883",
            "-v",
            str(CERT) + ":/certs:ro",
            "-v",
            str(ROOT / ".edge/passwords") + ":/passwords:ro",
            "-v",
            str(conf) + ":/mosquitto/config/mosquitto.conf:ro",
            "eclipse-mosquitto:2",
        )
        containers.append("twinguard-phase7-lab-tls-mqtt")
        run(
            "docker",
            "run",
            "-d",
            "--name",
            "twinguard-phase7-lab-tls-https",
            "--network",
            "host",
            "-v",
            str(CERT) + ":/certs:ro",
            "-v",
            str(nginx) + ":/etc/nginx/nginx.conf:ro",
            "nginx:1.28-alpine",
        )
        containers.append("twinguard-phase7-lab-tls-https")
        time.sleep(2)
        context = ssl.create_default_context(cafile=str(CERT / "ca.pem"))
        with httpx.Client(verify=context, timeout=15) as client:
            r = client.get(
                "https://localhost:19443/api/v1/assets",
                headers={"Authorization": "Bearer " + secrets["viewer"]},
            )
            report["results"]["https_ca_verified_status"] = r.status_code
        try:
            httpx.get("https://localhost:19443/api/v1/assets", timeout=5)
            report["results"]["https_untrusted_ca_rejected"] = False
        except httpx.ConnectError:
            report["results"]["https_untrusted_ca_rejected"] = True
        client = mqtt_client("demo-iot", secrets["demo-iot"], "phase7-tls-client")
        connected = []
        client.tls_set(ca_certs=str(CERT / "ca.pem"))
        client.on_connect = lambda c, u, f, rc, p: connected.append(str(rc))
        client.connect("localhost", 19483)
        client.loop_start()
        time.sleep(1)
        client.disconnect()
        client.loop_stop()
        report["results"]["mqtt_tls_verified_connection"] = connected
        report["results"]["opcua"] = asyncio.run(opc_checks())
        report["status"] = "executed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = type(exc).__name__ + ": " + str(exc)[:350]
    finally:
        for name in containers:
            run("docker", "rm", "-f", name)
        (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
