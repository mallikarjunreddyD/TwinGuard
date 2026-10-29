"""Real browser + MQTT observer acceptance against the isolated simulation stack."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
import uuid
import httpx
from playwright.sync_api import sync_playwright
from twinguard.edge.contracts import Envelope
from twinguard.edge.protocols import mqtt_client

ROOT = Path(__file__).resolve().parents[1]


def run(output, url="http://localhost:19380"):
    output.mkdir(parents=True, exist_ok=True)
    screenshots = ROOT / "docs/demo-ux/screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    result = dict(
        started_at_utc=datetime.now(timezone.utc).isoformat(),
        checks={},
        screenshots=[],
        scenarios={},
        errors=[],
    )
    messages = []
    connected = threading.Event()
    observer = mqtt_client(
        "ingestion", secrets["ingestion"], "ux-observer-" + uuid.uuid4().hex[:12]
    )

    def on_connect(client, userdata, flags, code, properties):
        client.subscribe("twinguard/v1/plant-01/+/+/+", qos=1)
        connected.set()

    def on_message(client, userdata, message):
        try:
            env = Envelope.model_validate_json(message.payload)
            messages.append((time.time(), env))
        except Exception as exc:
            result["errors"].append("Invalid public MQTT envelope: " + type(exc).__name__)

    observer.on_connect, observer.on_message = on_connect, on_message
    observer.connect("localhost", 19383)
    observer.loop_start()
    assert connected.wait(15), "MQTT observer did not connect"
    client = httpx.Client(
        base_url=url, headers={"Authorization": "Bearer " + secrets["operator"]}, timeout=30
    )

    def api(path):
        response = client.get("/api/v1/" + path)
        response.raise_for_status()
        return response.json()

    def wait_status(ident, predicate, timeout=180):
        deadline = time.monotonic() + timeout
        latest = {}
        while time.monotonic() < deadline:
            latest = api("demo/sessions/" + ident + "/status")
            if latest["state"] == "failed":
                raise AssertionError("Controller failed: " + str(latest.get("error")))
            if predicate(latest):
                return latest
            time.sleep(0.25)
        raise AssertionError("Timed out waiting for actual session status: " + str(latest))

    def count(ident):
        return sum(env.provenance_id == ident for _, env in messages)

    def shot(page, name):
        page.screenshot(path=str(screenshots / name), full_page=True)
        result["screenshots"].append(str((screenshots / name).relative_to(ROOT)))

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
            page.goto(url)
            page.get_by_label("Access token").fill(secrets["operator"])
            page.get_by_role("button", name="Open operations console").click()
            page.get_by_role("button", name="BW-01", exact=True).wait_for(timeout=60000)
            page.locator('[data-model-loaded="true"]').wait_for(state="attached", timeout=60000)
            assert page.locator('[data-testid="plant-canvas"]').count() == 1
            result["checks"]["login_overview_actual_model"] = True
            shot(page, "after-overview-first.png")
            page.get_by_role("button", name="Simulation Lab", exact=True).click()
            page.locator("button.primary").wait_for(timeout=30000)
            shot(page, "after-simulation-idle.png")
            page.get_by_label("Include measured LiDAR / thermal inspections").uncheck()
            page.get_by_label("Playback speed").select_option("2")
            with page.expect_response(
                lambda response: (
                    response.url.endswith("/api/v1/demo/sessions")
                    and response.request.method == "POST"
                )
            ) as created:
                page.locator("button.primary").click()
            ident = created.value.json()["id"]
            page.wait_for_function(
                "id=>document.querySelector('.session-identity')?.textContent?.trim()===id",
                arg=ident,
                timeout=30000,
            )
            running = wait_status(
                ident, lambda s: s["state"] == "running" and s["accepted_observations"] >= 12
            )
            result["scenarios"]["healthy_session"] = ident
            shot(page, "after-simulation-running.png")
            result["checks"]["browser_start_actual_mqtt_and_edge"] = (
                count(ident) > 0 and running["accepted_observations"] > 0
            )
            page.get_by_role("button", name="Pause", exact=True).click()
            paused = wait_status(ident, lambda s: s["state"] == "paused")
            time.sleep(0.3)
            before = count(ident)
            time.sleep(1.5)
            assert count(ident) == before, "MQTT publication continued after pause acknowledgment"
            assert (
                api("demo/sessions/" + ident + "/status")["published_observations"]
                == paused["published_observations"]
            )
            result["checks"]["pause_suspends_actual_mqtt"] = True
            shot(page, "after-simulation-paused.png")
            page.get_by_role("button", name="Resume", exact=True).click()
            resumed = wait_status(
                ident,
                lambda s: (
                    s["state"] == "running"
                    and s["published_observations"] > paused["published_observations"]
                ),
            )
            assert resumed["id"] == ident
            result["checks"]["resume_same_session_and_epoch"] = (
                len({env.sequence_epoch for _, env in messages if env.provenance_id == ident}) == 1
            )
            page.get_by_role("button", name="Stop", exact=True).click()
            stopped = wait_status(ident, lambda s: s["state"] == "stopped")
            time.sleep(0.3)
            before = count(ident)
            time.sleep(1.2)
            assert count(ident) == before
            result["checks"]["stop_ends_publisher_only"] = (
                api("platform/health")["database"] == "connected" and observer.is_connected()
            )
            result["scenarios"]["healthy_final"] = stopped
            page.get_by_role("button", name="Open Measurements", exact=True).click()
            page.wait_for_function(
                "Number(document.querySelector('[data-testid=stored-series]')?.dataset.sampleCount||0)>0",
                timeout=30000,
            )
            shot(page, "after-measurements.png")
            result["checks"]["stored_values_survive_stop"] = (
                len(api("assets/BW-01/observations?demo_session=" + ident)) > 0
            )
            assert page.locator(".recharts-line-curve").count() > 0
            result["checks"]["actual_stored_chart_drawn"] = True
            page.get_by_role("button", name="Simulation Lab", exact=True).click()
            page.reload()
            page.locator(".session-identity").wait_for(timeout=30000)
            assert page.locator(".session-identity").inner_text().strip() == ident
            result["checks"]["browser_refresh_restores_durable_session"] = True
            page.get_by_role("button", name="Overview", exact=True).click()
            snapshot = api("snapshot")
            unknown = next(
                asset["asset_id"]
                for asset in snapshot["assets"]
                if asset["asset_id"] != "BW-01"
                and snapshot["conditions"]
                .get(asset["asset_id"], {})
                .get("assessment", {})
                .get("severity", "unknown")
                == "unknown"
            )
            page.get_by_role("button", name=unknown, exact=True).click()
            assert "Insufficient qualified" in page.locator(".condition-explanation").inner_text()
            shot(page, "after-unknown-asset.png")
            result["checks"]["unknown_asset_truthfully_explained"] = True
            page.get_by_role("button", name="BW-01", exact=True).click()
            shot(page, "after-selected-BW-01.png")
            for name in ["Monitoring", "Inspections", "Advisories", "Inspection Planning"]:
                page.get_by_role("button", name=name, exact=True).click()
                page.wait_for_timeout(500)
                shot(page, "after-" + name.lower().replace(" ", "-") + ".png")
            page.set_viewport_size({"width": 850, "height": 1100})
            page.get_by_role("button", name="Simulation Lab", exact=True).click()
            page.wait_for_timeout(500)
            assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth+2")
            shot(page, "after-tablet.png")
            result["checks"]["tablet_no_horizontal_overflow"] = True
            page.keyboard.press("Tab")
            result["checks"]["keyboard_focus_visible"] = page.evaluate(
                "document.activeElement instanceof HTMLElement && getComputedStyle(document.activeElement).outlineStyle!=='none'"
            )
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
        result["observed_public_envelopes"] = len(messages)
        result["status"] = (
            "passed"
            if result["checks"] and all(result["checks"].values()) and not result["errors"]
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output)["status"] == "passed" else 1)
