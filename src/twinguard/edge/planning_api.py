"""Authenticated recommendation/review endpoints, deliberately no execution endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from twinguard.inspection.contracts import InspectionPlanningRequest
from .api import user, require, db
from .storage import get, put, list_records, audit
from .planning import submit, get_plan, store

router = APIRouter(prefix="/api/v1/inspection-plans")


@router.post("", status_code=202)
def create(body: InspectionPlanningRequest, actor=Depends(user)):
    require(actor, ["operator", "admin"])
    try:
        return submit(db(), body, actor["actor"])
    except (ValueError, IntegrityError) as exc:
        raise HTTPException(409, str(exc)[:500]) from exc


@router.get("")
def history(limit: int = Query(50, ge=1, le=100), actor=Depends(user)):
    with db().connect() as c:
        return list_records(c, "inspection_plan", limit=limit)


@router.get("/requests/{ident}")
def request_status(ident: str, actor=Depends(user)):
    with db().connect() as c:
        result = get(c, "planning_request", ident)
    if not result:
        raise HTTPException(404, "Request missing")
    return result


@router.get("/{ident}")
def detail(ident: str, actor=Depends(user)):
    with db().connect() as c:
        result = get_plan(c, ident)
        review = get(c, "planning_review", ident)
    if not result:
        raise HTTPException(404, "Plan missing")
    return {**result, "review": review}


@router.get("/{ident}/{section}")
def section(ident: str, section: str, actor=Depends(user)):
    result = detail(ident, actor)
    if section in ("candidates", "explanation"):
        return result[section]
    if section == "coverage":
        with db().connect() as c:
            entry = get(c, "inspection_plan", ident)
            request = get(c, "planning_request", entry["request_id"])
        import numpy as np

        with np.load(store().path(entry["coverage_map_sha256"]), allow_pickle=False) as data:
            centers = data["centers_world_m"].tolist()
        return {
            "centers_world_m": centers,
            "no_go": request["config"]["no_go"],
            "allowed_volume": request["config"]["allowed_volume"],
            "start_world_m": request["config"]["start_world_m"],
            "predicted_cells": sorted(
                {i for s in result["steps"] for i in s["utility"]["new_cells"]}
            ),
            "actual_coverage": request["snapshot"]["coverage"],
            "map_uri": "/api/v1/artifacts/" + entry["coverage_map_sha256"],
            "semantics": "Predicted cells do not establish measured or qualified coverage",
        }
    raise HTTPException(404, "Unknown section")


class Review(BaseModel):
    decision: str = Field(pattern="^(approved_for_simulation|deferred|rejected)$")
    rationale: str = Field(min_length=3, max_length=1000)
    acknowledges_critical_process: bool = False


@router.post("/{ident}/review")
def review(ident: str, body: Review, actor=Depends(user)):
    require(actor, ["operator", "admin"])
    with db().begin() as c:
        result = get_plan(c, ident)
        if not result:
            raise HTTPException(404, "Plan missing")
        if body.decision == "approved_for_simulation" and result["status"] != "recommended":
            raise HTTPException(409, "No viable plan to approve")
        if (
            body.decision == "approved_for_simulation"
            and any(p["access"] == "review_required" for p in result["priorities"])
            and not body.acknowledges_critical_process
        ):
            raise HTTPException(422, "Explicit critical-process acknowledgment required")
        record = {
            **body.model_dump(),
            "actor": actor["actor"],
            "plan_id": ident,
            "scope": "software simulation only; no physical UAV authorization",
        }
        put(c, "planning_review", ident, record)
        audit(c, "planning_review", **record)
    return record
