from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.services.investigator import investigate, load_investigation
from apps.api.services.knowledge_base import search_knowledge
from database.models import Investigation
from database.session import get_db

router = APIRouter(prefix="/api")


@router.post("/investigate/{incident_id}")
def investigate_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return investigate(db, incident_id).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/investigations")
def list_investigations(db: Session = Depends(get_db)) -> list[dict]:
    return [{"investigation_id": row.investigation_id, "incident_id": row.incident_id, "agent": row.agent,
             "started_at": row.started_at.isoformat(), "completed_at": row.completed_at.isoformat() if row.completed_at else None}
            for row in db.scalars(select(Investigation).order_by(Investigation.started_at.desc())).all()]


def _trace(investigation_id: str, db: Session):
    value = load_investigation(db, investigation_id)
    if not value:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return value


@router.get("/investigations/{investigation_id}")
def investigation_detail(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    return _trace(investigation_id, db).model_dump(mode="json")


@router.get("/investigations/{investigation_id}/trace")
def investigation_trace(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return _trace(investigation_id, db).model_dump(mode="json")["tool_calls"]


@router.get("/investigations/{investigation_id}/evidence")
def investigation_evidence(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return _trace(investigation_id, db).model_dump(mode="json")["final_result"]["evidence"]


@router.get("/investigations/{investigation_id}/similar-incidents")
def similar_incidents(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return _trace(investigation_id, db).model_dump(mode="json")["final_result"]["historical_matches"]


@router.get("/investigations/{investigation_id}/hypotheses")
def hypotheses(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return _trace(investigation_id, db).model_dump(mode="json")["final_result"]["alternative_hypotheses"]


@router.get("/knowledge/search")
def knowledge_search(q: str) -> list[dict[str, str]]:
    return search_knowledge(q)