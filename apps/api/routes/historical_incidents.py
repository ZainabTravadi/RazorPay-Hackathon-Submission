from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.session import get_db
from apps.api.services.incident_service import list_historical_incidents

router = APIRouter(prefix="/api")


@router.get("/historical-incidents")
def get_historical_incidents(db: Session = Depends(get_db)) -> list[dict]:
    records = list_historical_incidents(db)
    return [
        {
            "incident_id": item.incident_id,
            "incident_type": item.incident_type,
            "fingerprint": item.fingerprint,
            "root_cause": item.root_cause,
            "resolution": item.resolution,
            "recovery_rate": item.recovery_rate,
            "revenue_impact": item.revenue_impact,
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
        }
        for item in records
    ]
