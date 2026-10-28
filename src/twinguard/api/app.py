from twinguard.edge.planning_api import router as planning_router
from twinguard.edge.api import router
from fastapi import FastAPI
from twinguard import __version__, SCHEMA_VERSION

app = FastAPI(title="TwinGuard Edge Platform", version=__version__)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"software_version": __version__, "schema_version": SCHEMA_VERSION}


@app.get("/capabilities")
def capabilities():
    return {
        "phase": 6,
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
            "registration",
            "geometric_change_detection",
            "operating_analytics",
            "thermal_residual_analysis",
            "evidence_fusion",
            "temporal_assessment",
            "advisory_replay",
            "edge_ingestion",
            "durable_processing",
            "dashboard",
            "inspection_planning",
        ],
        "pending": [
            "physical_validation",
        ],
    }


app.include_router(router)


app.include_router(planning_router)
