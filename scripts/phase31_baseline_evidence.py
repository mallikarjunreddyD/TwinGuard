import json
import hashlib
import shutil
from pathlib import Path
from twinguard.analytics.pipeline import save_json

root = Path("experiments/outputs/phase3_1/baseline-reproduction")
old = json.loads(Path("docs/phase3_e1_results.json").read_text())
new = json.loads((root / "report.json").read_text())
differences = {}
for method in ["B1", "B2", "B3"]:
    differences[method] = {
        k: [old["metrics"][method][k], new["metrics"][method][k]]
        for k in [
            "recall",
            "false_positive_rate",
            "region_precision",
            "inconclusive_fraction",
            "translation_error_mm_mean",
        ]
    }
source = json.loads(Path("docs/phase3_1/baseline_source.json").read_text())
source.update(
    reproduced_report=str((root / "report.json").resolve()),
    runtime_s=new["runtime_s"],
    metrics=new["metrics"],
    comparison=differences,
    manifests={
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "datasets").glob("*/manifest.json")
    },
    calibration=json.loads((root / "geometry_calibration.json").read_text()),
    sensor_presets={
        level: json.loads(Path(f"configs/sensing/{level}.yaml").read_text())["lidar"]
        for level in ["L0", "L1", "L2"]
    },
)
save_json(Path("docs/phase3_1/baseline_v1.json"), source)
shutil.copy2(root / "report.json", "docs/phase3_1/baseline_results.json")
Path("docs/phase3_1/baseline_v1.sha256").write_text(
    hashlib.sha256(Path("docs/phase3_1/baseline_v1.json").read_bytes()).hexdigest() + "\n"
)
print(differences)
