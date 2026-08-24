from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.services.replay import build_replay, build_replay_event
from database.session import get_db

router = APIRouter(prefix="/api")


def _replay(function, *args):
    try:
        return function(*args)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/incidents/{incident_id}/replay")
def incident_replay(incident_id: str, db: Session = Depends(get_db)) -> dict:
    return _replay(build_replay, db, incident_id).model_dump(mode="json")


@router.get("/incidents/{incident_id}/replay/events")
def incident_replay_events(incident_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return [event.model_dump(mode="json") for event in _replay(build_replay, db, incident_id).events]


@router.get("/incidents/{incident_id}/replay/{event_id}")
def incident_replay_event(incident_id: str, event_id: str, db: Session = Depends(get_db)) -> dict:
    return _replay(build_replay_event, db, incident_id, event_id).model_dump(mode="json")
