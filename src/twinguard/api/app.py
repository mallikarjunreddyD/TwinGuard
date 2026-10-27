from fastapi import FastAPI
from twinguard import __version__, SCHEMA_VERSION

app = FastAPI(title="TwinGuard Phase 0", version=__version__)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"software_version": __version__, "schema_version": SCHEMA_VERSION}


@app.get("/capabilities")
def capabilities():
    return {
        "phase": 0,
        "implemented": [
            "contracts",
            "configuration_validation",
            "spatial_transforms",
            "utc_utilities",
            "schema_export",
        ],
        "pending": [
            "plant_simulation",
            "virtual_sensing",
            "registration",
            "anomaly_detection",
            "evidence_fusion",
            "inspection_planning",
            "dashboard",
            "physical_validation",
        ],
    }
