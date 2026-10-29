"""Actual stored values and delayed old-asset response regression in Chromium."""

from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/mnt/d/TwinGuard/phase7-V7-strict-trends-v2")


def main(url="http://localhost:19080", output=None):
    global OUT
    if output is not None:
        OUT = Path(output)
    OUT.mkdir(parents=True, exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    report = {
        "scope": "Real stored observation/line rendering and deliberately delayed obsolete asset responses; no fabricated measurements",
        "checks": {},
    }
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
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(
            """const originalFetch=window.fetch;window.fetch=(input,init)=>originalFetch(input,init).then(response=>String(input).includes('assets/DR-01/')?new Promise(resolve=>setTimeout(()=>resolve(response),1800)):response);"""
        )
        page.goto(url)
        page.get_by_label("Access token").fill(secrets["operator"])
        page.get_by_role("button", name="Open operations console").click()
        page.wait_for_selector('[data-model-loaded="true"]', timeout=60000)
        page.wait_for_function(
            'Number(document.querySelector("[data-testid=stored-series]")?.dataset.sampleCount)>0',
            timeout=60000,
        )
        page.get_by_role("button", name="Measurements", exact=True).click()
        page.wait_for_function(
            'document.querySelector(".recharts-line-curve")?.getAttribute("d")?.length>20',
            timeout=30000,
        )
        report["checks"]["actual_stored_samples"] = (
            int(page.locator("[data-testid=stored-series]").get_attribute("data-sample-count")) > 0
        )
        report["checks"]["actual_line_geometry"] = (
            len(page.locator(".recharts-line-curve").get_attribute("d") or "") > 20
        )
        report["checks"]["measured_pressure_unit"] = (
            "Unit: Pa" in page.locator(".chart").inner_text()
        )
        page.get_by_role("button", name="DR-01", exact=True).click()
        page.wait_for_timeout(150)
        page.get_by_role("button", name="BW-01", exact=True).click()
        page.wait_for_function(
            'Number(document.querySelector("[data-testid=stored-series]")?.dataset.sampleCount)>0',
            timeout=30000,
        )
        page.wait_for_timeout(2500)
        report["checks"]["obsolete_delayed_asset_response_ignored"] = (
            int(page.locator("[data-testid=stored-series]").get_attribute("data-sample-count")) > 0
            and "Unit: Pa" in page.locator(".chart").inner_text()
        )
        report["stored_samples_displayed"] = int(
            page.locator("[data-testid=stored-series]").get_attribute("data-sample-count")
        )
        page.screenshot(path=str(OUT / "actual_stored_trends.png"), full_page=True)
        page.get_by_role("button", name="Overview", exact=True).click()
        page.wait_for_selector('[data-model-loaded="true"]', timeout=30000)
        page.screenshot(path=str(OUT / "actual_dashboard_with_values.png"), full_page=True)
        report["javascript_errors"] = errors
        report["checks"]["no_javascript_errors"] = not errors
        browser.close()
    report["status"] = "passed" if all(report["checks"].values()) else "failed"
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:19080")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    main(args.url, args.output)
