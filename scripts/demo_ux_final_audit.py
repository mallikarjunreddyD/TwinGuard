"""Final live page, plan, console, responsive and isolation audit (no mocks)."""

import json
import re
import traceback
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone
import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "docs/demo-ux/final-runtime-audit.json"
    result = {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "errors": [],
        "console_errors": [],
        "console_warnings": [],
        "http_errors": [],
        "failed_requests": [],
    }
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    client = httpx.Client(
        base_url="http://localhost:19380",
        headers={"Authorization": "Bearer " + secrets["operator"]},
        timeout=30,
    )

    def api(path):
        r = client.get("/api/v1/" + path)
        r.raise_for_status()
        return r.json()

    def docker(*args):
        return subprocess.check_output(["docker", *args], text=True)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                args=[
                    "--no-sandbox",
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                ]
            )
            page = browser.new_page(
                viewport={"width": 1500, "height": 1050}, timezone_id="Asia/Kolkata"
            )
            page.on("pageerror", lambda e: result["errors"].append(str(e)))
            page.on(
                "console",
                lambda m: (
                    result["console_errors" if m.type == "error" else "console_warnings"].append(
                        m.text
                    )
                    if m.type in ("error", "warning")
                    else None
                ),
            )
            page.on(
                "response",
                lambda r: (
                    result["http_errors"].append({"url": r.url.split("?")[0], "status": r.status})
                    if r.status >= 400
                    else None
                ),
            )
            page.on(
                "requestfailed",
                lambda r: result["failed_requests"].append(
                    {"url": r.url.split("?")[0], "failure": r.failure}
                ),
            )
            page.goto("http://localhost:19380")
            page.get_by_label("Access token").fill(secrets["operator"])
            page.get_by_role("button", name="Open operations console").click()
            page.locator('[data-model-loaded="true"]').wait_for(state="attached", timeout=60000)
            page.get_by_role("button", name="Inspection Planning", exact=True).click()
            create = page.get_by_role(
                "button",
                name=re.compile("^(Request inspection plan|Replan from current public evidence)$"),
            )
            create.wait_for(timeout=30000)
            previous = {p["plan_id"] for p in api("inspection-plans")}
            with page.expect_response(
                lambda r: r.request.method == "POST" and r.url.endswith("/api/v1/inspection-plans")
            ) as response:
                create.click()
            assert response.value.status == 202
            deadline = time.monotonic() + 180
            plans = []
            while time.monotonic() < deadline:
                plans = [p for p in api("inspection-plans") if p["plan_id"] not in previous]
                if plans:
                    break
                page.wait_for_timeout(1000)
            assert plans, "Actual planning worker produced no plan"
            plan = api("inspection-plans/" + plans[0]["plan_id"])
            result["plan"] = {
                k: plan.get(k)
                for k in (
                    "plan_id",
                    "status",
                    "steps",
                    "expected_new_usable_area_m2",
                    "estimated_duration_s",
                    "snapshot_hash",
                    "policy_hash",
                )
            }
            page.get_by_role(
                "button", name="Replan from current public evidence", exact=True
            ).wait_for(timeout=60000)
            page.locator('[data-model-loaded="true"]').wait_for(state="attached", timeout=60000)
            result["checks"]["actual_planning_worker_and_reference_geometry"] = True
            result["checks"]["planned_sensor_positions_and_predicted_coverage"] = (
                len(plan["steps"]) > 0
            )
            page.screenshot(
                path=str(ROOT / "docs/demo-ux/screenshots/after-plan-generated.png"), full_page=True
            )
            result["pages"] = []
            for name in (
                "Overview",
                "Measurements",
                "Inspections",
                "Advisories",
                "Monitoring",
                "Inspection Planning",
                "Simulation Lab",
            ):
                page.get_by_role("button", name=name, exact=True).click()
                page.wait_for_timeout(2500)
                assert page.locator("main").inner_text().strip()
                result["pages"].append(name)
            page.get_by_role("button", name="Overview", exact=True).click()
            page.locator('[data-model-loaded="true"]').wait_for(state="attached", timeout=60000)
            canvas = page.locator('[data-testid="plant-canvas"]')
            old = page.locator('.asset-strip button[aria-pressed="true"]').inner_text()
            canvas.focus()
            page.keyboard.press("ArrowRight")
            new = page.locator('.asset-strip button[aria-pressed="true"]').inner_text()
            result["checks"]["keyboard_geometry_selection"] = new != old
            tokens = page.evaluate(
                """() => {let s=getComputedStyle(document.documentElement); return Object.fromEntries(['text','muted','accent','critical','warning','normal','unknown','canvas','surface'].map(k=>[k,s.getPropertyValue('--'+k).trim()]))}"""
            )

            def luminance(h):
                h = h.lstrip("#")
                h = "".join(c * 2 for c in h) if len(h) == 3 else h
                cs = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
                cs = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in cs]
                return sum(x * w for x, w in zip(cs, (0.2126, 0.7152, 0.0722)))

            result["text_contrast"] = {}
            for fg in ("text", "muted", "accent", "critical", "warning", "normal", "unknown"):
                ratios = [
                    (max(luminance(tokens[fg]), luminance(tokens[bg])) + 0.05)
                    / (min(luminance(tokens[fg]), luminance(tokens[bg])) + 0.05)
                    for bg in ("surface", "canvas")
                ]
                result["text_contrast"][fg] = round(min(ratios), 2)
            result["checks"]["text_token_contrast_at_least_4_5"] = (
                min(result["text_contrast"].values()) >= 4.5
            )
            result["checks"]["seven_pages_live_without_http_or_console_errors"] = not (
                result["http_errors"] or result["console_errors"] or result["errors"]
            )
            result["responsive"] = {}
            for width in (1500, 850, 390):
                page.set_viewport_size({"width": width, "height": 1000})
                page.wait_for_timeout(500)
                overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
                result["responsive"][str(width)] = {"horizontal_overflow": overflow}
                assert not overflow, f"Overview overflow at {width}"
            browser.close()
        api_id = docker("ps", "-q", "--filter", "name=^twinguard-demo-ux-api-1$").strip()
        controller_id = docker(
            "ps", "-q", "--filter", "name=^twinguard-demo-ux-simulation-controller-1$"
        ).strip()
        modules = json.loads(
            docker(
                "exec",
                api_id,
                "python",
                "-c",
                "import importlib.util,json;print(json.dumps({m:importlib.util.find_spec('twinguard.'+m) is None for m in ['demo','plant','sensing','evaluation']}))",
            )
        )
        result["api_modules_absent"] = modules
        result["checks"]["privileged_modules_absent_from_api"] = all(modules.values())
        inspected = json.loads(docker("inspect", api_id, controller_id))
        result["containers"] = [
            {
                "name": c["Name"],
                "user": c["Config"]["User"],
                "memory_bytes": c["HostConfig"]["Memory"],
                "nano_cpus": c["HostConfig"]["NanoCpus"],
                "pids_limit": c["HostConfig"]["PidsLimit"],
                "mounts": [
                    {"destination": m["Destination"], "writable": m["RW"]} for m in c["Mounts"]
                ],
            }
            for c in inspected
        ]
        result["checks"]["no_docker_socket_nonroot_and_private_demo_mount"] = all(
            docker("exec", c["Id"], "id", "-u").strip() == "10001"
            and all(m["Destination"] != "/var/run/docker.sock" for m in c["Mounts"])
            for c in inspected
        ) and not any(m["Destination"] == "/demo-data" for m in inspected[0]["Mounts"])
        result["checks"]["responsive_widths_no_overflow"] = all(
            not v["horizontal_overflow"] for v in result["responsive"].values()
        )
        result["status"] = "passed" if all(result["checks"].values()) else "failed"
    except Exception as exc:
        traceback.print_exc()
        result["errors"].append(type(exc).__name__ + ": " + str(exc))
        result["status"] = "failed"
    finally:
        out.write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in ("status", "checks", "errors", "http_errors", "console_errors")
                }
            )
        )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
