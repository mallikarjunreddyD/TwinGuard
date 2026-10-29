"""Resume already executed scenario checks; exercise remaining real recovery/profile cases."""

from datetime import datetime, timezone
import hashlib
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


def run():
    source = ROOT / ".demo-data/scenarios-initial/report.json"
    result = json.loads(source.read_text())
    assert len(result["checks"]) == 5 and all(result["checks"].values())
    result.update(
        errors=[],
        resumed_from=dict(
            path=str(source.relative_to(ROOT)),
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            reason="Retain five actually executed successful checks; repair optional-phase polling and execute only remaining cases",
        ),
        started_resume_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    out = ROOT / ".demo-data/scenarios-resumed"
    out.mkdir(exist_ok=True)
    shots = ROOT / "docs/demo-ux/screenshots"
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    messages = []
    connected = threading.Event()
    observer = mqtt_client(
        "ingestion", secrets["ingestion"], "ux-recovery-" + uuid.uuid4().hex[:10]
    )

    def connect(client, userdata, flags, code, props):
        client.subscribe("twinguard/v1/plant-01/+/+/+", qos=1)
        connected.set()

    def receive(client, userdata, message):
        try:
            messages.append(Envelope.model_validate_json(message.payload))
        except Exception as exc:
            result["errors"].append(type(exc).__name__)

    observer.on_connect = connect
    observer.on_message = receive
    observer.connect("localhost", 19383)
    observer.loop_start()
    assert connected.wait(15)
    api = httpx.Client(
        base_url="http://localhost:19380/api/v1/",
        headers={"Authorization": "Bearer " + secrets["operator"]},
        timeout=30,
    )

    def get(path):
        response = api.get(path)
        response.raise_for_status()
        return response.json()

    def wait(fn, timeout=180):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = fn()
            if value:
                return value
            time.sleep(0.25)
        raise AssertionError("Timed out waiting for an executed outcome")

    def status(ident):
        row = get("demo/sessions/" + ident + "/status")
        if row["state"] == "failed":
            raise AssertionError(row.get("error"))
        return row

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
            page.on("pageerror", lambda e: result["errors"].append(str(e)))
            page.goto("http://localhost:19380")
            page.get_by_label("Access token").fill(secrets["operator"])
            page.get_by_role("button", name="Open operations console").click()
            page.get_by_role("button", name="Simulation Lab", exact=True).click()

            def start(label, speed):
                page.locator(".scenario").filter(has_text=label).click()
                page.get_by_label("Playback speed").select_option(str(speed))
                checkbox = page.get_by_label("Include measured LiDAR / thermal inspections")
                if checkbox.is_enabled():
                    checkbox.uncheck()
                with page.expect_response(
                    lambda r: r.url.endswith("/api/v1/demo/sessions") and r.request.method == "POST"
                ) as response:
                    page.locator("button.primary").click()
                ident = response.value.json()["id"]
                page.wait_for_function(
                    "id=>document.querySelector('.session-identity')?.textContent?.trim()===id",
                    arg=ident,
                    timeout=30000,
                )
                print("Started remaining", label, ident, flush=True)
                return ident

            ident = start("Sensor Interruption", 10)
            wait(lambda: status(ident).get("phase") == "source_interruption", 90)
            page.screenshot(
                path=str(shots / "after-source-interruption-running.png"), full_page=True
            )
            final = wait(lambda: s if (s := status(ident))["state"] == "completed" else None, 90)
            inactive = wait(
                lambda: next(
                    (
                        h
                        for h in get("monitoring/health")
                        if h["source_id"] == "demo-iot" and h["connection"] != "connected"
                    ),
                    None,
                ),
                30,
            )
            assert final["accepted_observations"] > 0
            gap = (
                datetime.fromisoformat(final["ended_at"])
                - datetime.fromisoformat(final["last_delivery"]["emitted_at"])
            ).total_seconds()
            assert gap >= 16
            result["checks"]["interruption_real_missing_source"] = True
            result["scenarios"]["interruption"] = dict(
                session=final, source=inactive, observed_end_minus_last_emission_s=gap
            )
            page.get_by_role("button", name="Monitoring", exact=True).click()
            page.screenshot(path=str(shots / "after-monitoring-interruption.png"), full_page=True)
            page.get_by_role("button", name="Simulation Lab", exact=True).click()
            crash = start("Healthy Operation", 1)
            wait(lambda: status(crash)["accepted_observations"] >= 10, 90)
            count_before = len(get("demo/sessions"))
            subprocess.run(
                ["docker", "restart", "twinguard-demo-ux-simulation-controller-1"],
                check=True,
                capture_output=True,
            )
            failed = wait(
                lambda: (
                    s
                    if (s := get("demo/sessions/" + crash + "/status"))["state"] == "failed"
                    else None
                ),
                60,
            )
            time.sleep(0.5)
            before = sum(m.provenance_id == crash for m in messages)
            time.sleep(1.5)
            assert sum(m.provenance_id == crash for m in messages) == before
            assert len(get("demo/sessions")) == count_before
            result["checks"]["controller_restart_no_silent_republication"] = True
            result["scenarios"]["controller_restart"] = failed
            viewer = browser.new_page(viewport={"width": 1300, "height": 1000})
            viewer.goto("http://localhost:19380")
            viewer.get_by_label("Access token").fill(secrets["viewer"])
            viewer.get_by_role("button", name="Open operations console").click()
            viewer.get_by_role("button", name="Simulation Lab", exact=True).click()
            wait(lambda: viewer.locator("button.primary").is_disabled(), 30)
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
            review = browser.new_page(viewport={"width": 1300, "height": 1000})
            review.goto("http://localhost:19390")
            review.get_by_label("Access token").fill(secrets["operator"])
            review.get_by_role("button", name="Open operations console").click()
            review.get_by_role("button", name="Simulation Lab", exact=True).click()
            review.get_by_text(
                "Simulation execution is disabled in this deployment.", exact=True
            ).wait_for(timeout=30000)
            assert review.locator("button.primary").is_disabled()
            denied = review.request.post(
                "http://localhost:19390/api/v1/demo/sessions",
                headers={
                    "Authorization": "Bearer " + secrets["operator"],
                    "Idempotency-Key": str(uuid.uuid4()),
                },
                data={},
            )
            assert denied.status == 403
            assert len(get("demo/sessions")) == count_before
            result["checks"]["site_review_browser_and_server_reject_execution"] = True
            review.screenshot(path=str(shots / "after-site-review-disabled.png"), full_page=True)
            review.close()
            observations = get("platform/health")["observations"]
            event = result["scenarios"]["critical_event"]["event_id"]
            subprocess.run(
                ["docker", "restart", "twinguard-demo-ux-api-1", "twinguard-demo-ux-frontend-1"],
                check=True,
                capture_output=True,
            )

            def api_ready():
                try:
                    return api.get("platform/health").status_code == 200
                except httpx.HTTPError:
                    return False

            wait(api_ready, 90)
            assert get("platform/health")["observations"] == observations
            assert get("events/" + event)["event_id"] == event
            assert len(get("demo/sessions")) == count_before
            result["checks"]["api_dashboard_restart_retains_records"] = True
            page.reload()
            page.get_by_role("button", name="Simulation Lab", exact=True).wait_for(timeout=30000)
            browser.close()
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
        for value in secrets.values():
            error = error.replace(value, "[redacted]")
        result["errors"].append(error)
        raise
    finally:
        observer.disconnect()
        observer.loop_stop()
        api.close()
        result["status"] = (
            "passed"
            if len(result["checks"]) >= 10
            and all(result["checks"].values())
            and not result["errors"]
            else "failed"
        )
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        result["resumed_observed_public_envelopes"] = len(messages)
        (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {"status": result["status"], "checks": result["checks"], "errors": result["errors"]}
            ),
            flush=True,
        )

    return result


if __name__ == "__main__":
    raise SystemExit(0 if run()["status"] == "passed" else 1)
