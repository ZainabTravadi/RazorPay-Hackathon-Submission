from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import HistoricalIncident, Incident, Payment
from data.generator.generate import generate_payments
from ml.anomaly.detector import detect_incidents
from ml.fingerprinting.fingerprint import build_fingerprint, canonical_error_family


def get_incident_by_id(db: Session, incident_id: str) -> Incident | None:
    return db.get(Incident, incident_id)


def list_active_incidents(db: Session) -> list[Incident]:
    return db.scalars(select(Incident).order_by(Incident.detected_at.desc())).all()


def list_historical_incidents(db: Session) -> list[HistoricalIncident]:
    return db.scalars(select(HistoricalIncident).order_by(HistoricalIncident.timestamp.desc())).all()


def persist_incident(db: Session, payload: dict[str, Any]) -> Incident:
    started_at = payload["started_at"]
    ended_at = payload.get("ended_at")
    detected_at = payload["detected_at"]
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at)
    if isinstance(ended_at, str):
        ended_at = datetime.fromisoformat(ended_at)
    if isinstance(detected_at, str):
        detected_at = datetime.fromisoformat(detected_at)

    incident = Incident(
        incident_id=payload["incident_id"],
        incident_type=payload["incident_type"],
        severity=payload["severity"],
        status=payload["status"],
        started_at=started_at,
        ended_at=ended_at,
        detected_at=detected_at,
        anomaly_score=float(payload["anomaly_score"]),
        affected_transactions=int(payload["affected_transactions"]),
        affected_merchants=int(payload["affected_merchants"]),
        revenue_at_risk=float(payload["revenue_at_risk"]),
        primary_provider=payload.get("primary_provider"),
        primary_payment_method=payload.get("primary_payment_method"),
        primary_region=payload.get("primary_region"),
        fingerprint=payload.get("fingerprint"),
        description=payload.get("description"),
    )
    db.merge(incident)
    db.commit()
    return incident


def create_incident_from_dataset(db: Session, df, *, incident_type: str = "provider_outage") -> Incident:
    incidents = detect_incidents(df)
    if not incidents:
        raise ValueError("No incident detected for the provided dataset")

    selected = None
    for item in incidents:
        if item["incident_type"] == incident_type or item["incident_type"].startswith("provider"):
            selected = item
            break
    if selected is None:
        selected = incidents[0]

    incident = Incident(
        incident_id=selected["incident_id"],
        incident_type=selected["incident_type"],
        severity=selected["severity"],
        status=selected["status"],
        started_at=datetime.fromisoformat(selected["started_at"]),
        ended_at=datetime.fromisoformat(selected["ended_at"]) if selected.get("ended_at") else None,
        detected_at=datetime.fromisoformat(selected["detected_at"]),
        anomaly_score=float(selected["anomaly_score"]),
        affected_transactions=int(selected["affected_transactions"]),
        affected_merchants=int(selected["affected_merchants"]),
        revenue_at_risk=float(selected["revenue_at_risk"]),
        primary_provider=selected.get("primary_provider"),
        primary_payment_method=selected.get("primary_payment_method"),
        primary_region=selected.get("primary_region"),
        fingerprint=selected.get("fingerprint"),
        description=selected.get("description"),
    )
    db.merge(incident)
    db.commit()
    return incident


def seed_active_incident(db: Session) -> Incident | None:
    df = generate_payments(events=5000, seed=11)
    df2 = df.copy()
    df2.loc[df2["provider"] == "Provider B", "status"] = "failed"
    df2.loc[df2["provider"] == "Provider B", "error_code"] = "provider_outage"
    df2.loc[df2["provider"] == "Provider B", "latency_ms"] = 9000
    incident = create_incident_from_dataset(db, df2, incident_type="provider_outage")
    return incident
