from fastapi import FastAPI
from twinguard import __version__, SCHEMA_VERSION

app = FastAPI(title="TwinGuard Phase 2", version=__version__)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"software_version": __version__, "schema_version": SCHEMA_VERSION}


@app.get("/capabilities")
def capabilities():
    return {
        "phase": 2,
        "implemented": [
            "contracts",
            "configuration_validation",
            "spatial_transforms",
            "utc_utilities",
            "schema_export",
            "plant_simulation",
            "fault_injection",
            "geometry_export",
            "virtual_sensing",
            "lidar_raycasting",
            "thermal_projection",
            "iot_acquisition",
        ],
        "pending": [
            "registration",
            "anomaly_detection",
            "evidence_fusion",
            "inspection_planning",
            "dashboard",
            "physical_validation",
        ],
    }
