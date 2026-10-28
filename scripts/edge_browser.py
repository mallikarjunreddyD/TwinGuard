"""Real Chromium integration check and screenshots against the running local stack."""

import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(output, url="http://localhost:18780"):
    output.mkdir(parents=True, exist_ok=True)
    secrets = json.loads(Path(".edge/secrets.json").read_text())
    result = {"errors": [], "checks": {}, "screenshots": [], "started_wall_s": time.time()}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
            ],
        )
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.on("pageerror", lambda e: result["errors"].append(str(e)))
        requests = []
        page.on("request", lambda r: requests.append(r.url))
        page.goto(url)
        page.get_by_label("Access token").fill(secrets["operator"])
        page.get_by_role("button", name="Open operations console").click()
        page.wait_for_selector('[data-model-loaded="true"]', timeout=60000)
        page.wait_for_timeout(1500)
        result["checks"]["model_loaded"] = page.locator('[data-testid="plant-canvas"]').count() == 1
        result["checks"]["actual_assets"] = (
            page.get_by_role("button", name="BW-01", exact=True).count() == 1
        )
        page.screenshot(path=str(output / "E4-7_dashboard.png"), full_page=True)
        result["screenshots"].append("E4-7_dashboard.png")
        # Both the scene raycast and asset strip share backend selection.
        page.get_by_role("button", name="DR-01", exact=True).click()
        page.wait_for_timeout(200)
        result["checks"]["asset_selection"] = "DR-01" in page.locator(".detail").inner_text()
        page.get_by_role("button", name="BW-01", exact=True).click()
        page.get_by_role("button", name="Measurements", exact=True).click()
        result["checks"]["stored_trend_chart"] = page.locator(".recharts-wrapper").count() > 0
        page.screenshot(path=str(output / "E4_measurements.png"), full_page=True)
        page.get_by_role("button", name="Inspections", exact=True).click()
        page.wait_for_timeout(500)
        result["checks"]["thermal_image"] = (
            page.locator('[data-testid="thermal-image"]').count() > 0
        )
        result["checks"]["geometric_measurement"] = (
            "localized_relative" in page.locator("main").inner_text()
        )
        page.screenshot(path=str(output / "E4_inspections.png"), full_page=True)
        page.get_by_role("button", name="Monitoring", exact=True).click()
        result["checks"]["monitoring_view"] = "Clock / basis" in page.locator("main").inner_text()
        page.screenshot(path=str(output / "E4_monitoring.png"), full_page=True)
        page.get_by_role("button", name="Advisories", exact=True).click()
        result["checks"]["evidence_trace"] = (
            "Evidence & policy trace" in page.locator("main").inner_text()
        )
        result["checks"]["red_advisory"] = "RED" in page.locator("main").inner_text()
        buttons = page.get_by_role("button", name="Acknowledge review", exact=True)
        if buttons.count():
            buttons.first.click()
            page.wait_for_timeout(800)
            result["checks"]["acknowledgment"] = "acknowledged" in page.locator("main").inner_text()
        page.screenshot(path=str(output / "E4-8_critical_trace.png"), full_page=True)
        # A real interrupted browser connection resumes the durable stream with its cursor.
        before = page.evaluate("window.__tgLastStreamId || 0")
        page.context.set_offline(True)
        page.wait_for_timeout(700)
        page.context.set_offline(False)
        page.wait_for_timeout(4000)
        after = page.evaluate("window.__tgLastStreamId || 0")
        result["checks"]["stream_reconnect"] = after > before
        result["browser_last_delivery_wall_s"] = time.time()
        result["external_requests"] = [u for u in requests if not u.startswith(url)]
        result["render_metrics"] = page.evaluate(
            '({dom:document.querySelectorAll("*").length,heap:performance.memory?.usedJSHeapSize,stream:window.__tgLastStreamId})'
        )
        browser.close()
    result["finished_wall_s"] = time.time()
    (output / "browser.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["checks"], result["errors"])
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("docs/figures/phase5"))
    args = p.parse_args()
    run(args.output)
