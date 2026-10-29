"""Executed preset scenarios, roles and recovery; no frontend status mocks."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid
import httpx
from playwright.sync_api import sync_playwright
from twinguard.edge.contracts import Envelope
from twinguard.edge.protocols import mqtt_client

ROOT = Path(__file__).resolve().parents[1]


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    shots = ROOT / "docs/demo-ux/screenshots"
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    result = dict(
        checks={}, scenarios={}, errors=[], started_at_utc=datetime.now(timezone.utc).isoformat()
    )
    messages = []
    ready = threading.Event()
    observer = mqtt_client(
        "ingestion", secrets["ingestion"], "ux-scenarios-" + uuid.uuid4().hex[:10]
    )

    def connected(client, userdata, flags, code, props):
        client.subscribe("twinguard/v1/plant-01/+/+/+", qos=1)
        ready.set()

    def received(client, userdata, message):
        messages.append(Envelope.model_validate_json(message.payload))

    observer.on_connect, observer.on_message = connected, received
    observer.connect("localhost", 19383)
    observer.loop_start()
    assert ready.wait(15)
    client = httpx.Client(
        base_url="http://localhost:19380/api/v1/",
        headers={"Authorization": "Bearer " + secrets["operator"]},
        timeout=30,
    )

    def get(path):
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    def wait(fn, timeout=180):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = fn()
            if value:
                return value
            time.sleep(0.3)
        raise AssertionError("Timed out waiting for actual executed outcome")

    def status(ident):
        row = get("demo/sessions/" + ident + "/status")
        if row["state"] == "failed":
            raise AssertionError(row.get("error"))
        return row

    def screenshot(page, name):
        page.screenshot(path=str(shots / name), full_page=True)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                ],
            )
            page = browser.new_page(
                viewport={"width": 1500, "height": 1050}, timezone_id="Asia/Kolkata"
            )
            page.on("pageerror", lambda err: result["errors"].append(str(err)))
            page.goto("http://localhost:19380")
            page.get_by_label("Access token").fill(secrets["operator"])
            page.get_by_role("button", name="Open operations console").click()
            page.get_by_role("button", name="Simulation Lab", exact=True).click()

            def start(label, speed=10, inspections=True):
                page.locator(".scenario").filter(has_text=label).click()
                page.get_by_label("Playback speed").select_option(str(speed))
                checkbox = page.get_by_label("Include measured LiDAR / thermal inspections")
                if checkbox.is_enabled():
                    checkbox.set_checked(inspections)
                with page.expect_response(
                    lambda response: (
                        response.url.endswith("/api/v1/demo/sessions")
                        and response.request.method == "POST"
                    )
                ) as response:
                    page.locator("button.primary").click()
                ident = response.value.json()["id"]
                page.wait_for_function(
                    "id=>document.querySelector('.session-identity')?.textContent?.trim()===id",
                    arg=ident,
                    timeout=30000,
                )
                print("Started", label, ident, flush=True)
                return ident

            def lab():
                page.get_by_role("button", name="Simulation Lab", exact=True).click()
                page.locator("button.primary").wait_for(timeout=30000)

            def stop(ident):
                page.get_by_role("button", name="Stop", exact=True).click()
                return wait(
                    lambda: status(ident) if status(ident)["state"] == "stopped" else None, 30
                )

            critical = start("Critical Pressure", 2, False)
            wait(lambda: status(critical)["accepted_observations"] > 0)

            def critical_event():
                return next(
                    (
                        event
                        for event in get("events?asset_id=BW-01")
                        if event["severity"] == "red"
                        and "pressure" in event["hazard_id"]
                        and any(critical in origin for origin in event.get("positive_origins", []))
                    ),
                    None,
                )

            event = wait(critical_event, 90)
            assert not any(m.kind == "inspection" for m in messages if m.provenance_id == critical)
            result["checks"]["critical_f1_without_uav"] = True
            result["scenarios"]["critical_event"] = event
            page.get_by_role("button", name="Overview", exact=True).click()
            wait(
                lambda: (
                    get("snapshot")["conditions"]
                    .get("BW-01", {})
                    .get("assessment", {})
                    .get("severity")
                    == "red"
                ),
                30,
            )
            screenshot(page, "after-overview-critical.png")
            page.get_by_role("button", name="Advisories", exact=True).click()
            article = page.locator('[data-event-id="' + event["event_id"] + '"]')
            article.get_by_role("button", name="Acknowledge review", exact=True).click()
            actions = wait(lambda: get("events/" + event["event_id"] + "/actions"), 30)
            assert actions[0]["actor"] == "operator-local"
            assert get("events/" + event["event_id"])["lifecycle"] != "resolved"
            article.get_by_text("Acknowledgment and lifecycle history", exact=True).click()
            article.get_by_text("operator-local", exact=False).wait_for(timeout=30000)
            screenshot(page, "after-advisories-critical.png")
            result["checks"]["operator_acknowledgment_preserves_event"] = True
            lab()
            result["scenarios"]["critical_final"] = stop(critical)
            assert get("events/" + event["event_id"])["event_id"] == event["event_id"]
            for label, key in [
                ("Localized Deformation", "geometry"),
                ("Thermal Anomaly", "thermal"),
                ("Degraded Sensing", "degraded"),
            ]:
                lab()
                ident = start(label, 10, True)
                final = wait(
                    lambda: status(ident) if status(ident)["state"] == "completed" else None, 240
                )
                final = wait(
                    lambda: status(ident) if status(ident)["completed_inspections"] >= 1 else None,
                    240,
                )
                inspection = get("inspections/" + final["inspection_message_id"])
                assert inspection.get("geometric")
                if key == "thermal":
                    assert inspection.get("thermal_images")
                if key == "degraded":
                    assert final["configuration"]["fidelity"] == "L2"
                result["scenarios"][key] = dict(
                    session=final,
                    geometry_statuses=[g["status"] for g in inspection.get("geometric", [])],
                    geometric_regions=sum(
                        len(g.get("regions", [])) for g in inspection.get("geometric", [])
                    ),
                    thermal_statuses=[t["status"] for t in inspection.get("thermal", [])],
                )
                result["checks"][key + "_actual_inspection_processing"] = True
                page.get_by_role("button", name="Open Inspections", exact=True).click()
                page.get_by_label("Inspection", exact=True).select_option(
                    final["inspection_message_id"]
                )
                screenshot(page, "after-" + key + "-inspection.png")
            lab()
            interruption = start("Sensor Interruption", 10, False)
            wait(lambda: status(interruption).get("phase") == "source_interruption", 60)
            row = wait(
                lambda: (
                    status(interruption) if status(interruption)["state"] == "completed" else None
                ),
                60,
            )
            unavailable = wait(
                lambda: next(
                    (
                        h
                        for h in get("monitoring/health")
                        if h["source_id"] == "demo-iot" and h["connection"] != "connected"
                    ),
                    None,
                ),
                20,
            )
            result["checks"]["interruption_real_missing_source"] = True
            result["scenarios"]["interruption"] = dict(session=row, source=unavailable)
            page.get_by_role("button", name="Monitoring", exact=True).click()
            screenshot(page, "after-monitoring-interruption.png")
            # Active controller restart must not silently replay or duplicate sessions.
            lab()
            crash = start("Healthy Operation", 1, False)
            wait(lambda: status(crash)["accepted_observations"] >= 10)
            before_sessions = len(get("demo/sessions"))
            subprocess.run(
                ["docker", "restart", "twinguard-demo-ux-simulation-controller-1"],
                check=True,
                capture_output=True,
            )
            failed = wait(
                lambda: (
                    row
                    if (row := get("demo/sessions/" + crash + "/status"))["state"] == "failed"
                    else None
                ),
                60,
            )
            time.sleep(0.5)
            count = sum(m.provenance_id == crash for m in messages)
            time.sleep(1)
            assert sum(m.provenance_id == crash for m in messages) == count
            assert len(get("demo/sessions")) == before_sessions
            result["checks"]["controller_restart_no_silent_republication"] = True
            result["scenarios"]["controller_restart"] = failed
            # Viewer browser and actual HTTP gate; no fabricated disabled status.
            viewer = browser.new_page(viewport={"width": 1300, "height": 1000})
            viewer.goto("http://localhost:19380")
            viewer.get_by_label("Access token").fill(secrets["viewer"])
            viewer.get_by_role("button", name="Open operations console").click()
            viewer.get_by_role("button", name="Simulation Lab", exact=True).click()
            wait(lambda: viewer.locator("button.primary").is_disabled())
            denied = viewer.request.post(
                "http://localhost:19380/api/v1/demo/sessions",
                headers={
                    "Authorization": "Bearer " + secrets["viewer"],
                    "Idempotency-Key": str(uuid.uuid4()),
                },
                data={},
            )
            assert denied.status == 403
            result["checks"]["viewer_browser_and_api_reject_execution"] = True
            viewer.close()
            before_observations = get("platform/health")["observations"]
            event_id = event["event_id"]
            subprocess.run(
                ["docker", "restart", "twinguard-demo-ux-api-1", "twinguard-demo-ux-frontend-1"],
                check=True,
                capture_output=True,
            )

            def ready_api():
                try:
                    return client.get("platform/health").status_code == 200
                except httpx.HTTPError:
                    return False

            wait(ready_api, 90)
            assert get("platform/health")["observations"] == before_observations
            assert get("events/" + event_id)["event_id"] == event_id
            assert len(get("demo/sessions")) == before_sessions
            result["checks"]["api_dashboard_restart_retains_records"] = True
            page.reload()
            page.get_by_role("button", name="Simulation Lab", exact=True).wait_for(timeout=30000)
            browser.close()
    except Exception as exc:
        message = type(exc).__name__ + ": " + str(exc)
        for secret in secrets.values():
            message = message.replace(secret, "[redacted]")
        result["errors"].append(message)
        raise
    finally:
        observer.disconnect()
        observer.loop_stop()
        client.close()
        result["observed_mqtt_envelopes"] = len(messages)
        result["status"] = (
            "passed"
            if len(result["checks"]) >= 9
            and all(result["checks"].values())
            and not result["errors"]
            else "failed"
        )
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {"status": result["status"], "checks": result["checks"], "errors": result["errors"]}
            ),
            flush=True,
        )

    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    raise SystemExit(0 if run(a.output)["status"] == "passed" else 1)
