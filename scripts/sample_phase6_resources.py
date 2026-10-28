"""Observe cumulative OS CPU times and peak RSS of live E5 processes; sample containers."""

from pathlib import Path
import os
import json
import time
import subprocess
from datetime import datetime, timezone

out = Path("experiments/outputs/phase6-resource-observations")
out.mkdir(exist_ok=False)
seen = {}
samples = []
for iteration in range(1800):
    current = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            args = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            if "scripts/run_e5_shards.py" not in args or not args.startswith(
                (".venv/bin/python", "/home/")
            ):
                continue
            fields = (proc / "stat").read_text().split()
            status = (proc / "status").read_text().splitlines()
            rss = next((int(v.split()[1]) for v in status if v.startswith("VmHWM:")), None)
            item = {
                "pid": int(proc.name),
                "parent_pid": int(fields[3]),
                "user_cpu_s": int(fields[13]) / os.sysconf("SC_CLK_TCK"),
                "system_cpu_s": int(fields[14]) / os.sysconf("SC_CLK_TCK"),
                "observed_peak_rss_kib": rss,
            }
            seen[proc.name] = item
            current.append(item)
        except (OSError, ValueError, IndexError):
            pass
    if iteration % 5 == 0:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        containers = [
            json.loads(line) for line in result.stdout.splitlines() if "twinguard-phase6-" in line
        ]
        samples.append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "containers": containers,
                "E5_processes": current,
            }
        )
    (out / "processes.json").write_text(
        json.dumps(
            {
                "scope": "Cumulative OS process CPU at last observed sample; monitoring started partway through E5, terminal sample may precede exit",
                "processes": list(seen.values()),
            },
            indent=2,
        )
        + "\n"
    )
    (out / "samples.json").write_text(json.dumps(samples, indent=2) + "\n")
    if not current:
        break
    time.sleep(1)
