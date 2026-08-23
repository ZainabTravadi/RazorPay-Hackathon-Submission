from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.services.recovery import approve_and_simulate, calculate_impact, create_recovery, evaluate_policy, execute_simulation, reject_recovery, recommend_recovery
from database.session import get_db

router = APIRouter(prefix="/api")


def _run(function, *args):
    try:
        return function(*args)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/incidents/{incident_id}/impact")
def incident_impact(incident_id: str, db: Session = Depends(get_db)) -> dict:
    return _run(calculate_impact, db, incident_id).model_dump(mode="json")


@router.get("/incidents/{incident_id}/recovery-recommendation")
def recovery_recommendation(incident_id: str, db: Session = Depends(get_db)) -> dict:
    return _run(recommend_recovery, db, incident_id).model_dump(mode="json")


@router.get("/incidents/{incident_id}/recovery-policy")
def recovery_policy(incident_id: str, db: Session = Depends(get_db)) -> dict:
    return _run(evaluate_policy, db, incident_id).model_dump(mode="json")


@router.post("/incidents/{incident_id}/recovery")
def prepare_recovery(incident_id: str, db: Session = Depends(get_db)) -> dict:
    return _run(create_recovery, db, incident_id).model_dump(mode="json")


@router.post("/recoveries/{recovery_id}/approve")
def approve_recovery(recovery_id: str, db: Session = Depends(get_db)) -> dict:
    return _run(approve_and_simulate, db, recovery_id).model_dump(mode="json")


@router.post("/recoveries/{recovery_id}/execute")
def execute_recovery(recovery_id: str, db: Session = Depends(get_db)) -> dict:
    return _run(execute_simulation, db, recovery_id).model_dump(mode="json")


@router.post("/recoveries/{recovery_id}/reject")
def reject(recovery_id: str, db: Session = Depends(get_db)) -> dict:
    return _run(reject_recovery, db, recovery_id).model_dump(mode="json")