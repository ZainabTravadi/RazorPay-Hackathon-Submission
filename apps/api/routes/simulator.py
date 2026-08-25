from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from apps.api.services.incident_service import persist_incident, seed_active_incident
from database.models import Incident, Investigation, Payment, RecoveryAttemptRecord, RecoveryEventRecord, RecoveryExecutionRecord
from database.session import get_db
from data.generator.generate import generate_payments
from ml.anomaly.detector import detect_incidents

router = APIRouter(prefix="/api")


@router.post("/simulator/reset")
def reset_simulator(db: Session = Depends(get_db)) -> dict:
    db.execute(delete(RecoveryEventRecord))
    db.execute(delete(RecoveryAttemptRecord))
    db.execute(delete(RecoveryExecutionRecord))
    db.execute(delete(Incident))
    db.execute(delete(Investigation))
    db.query(Payment).filter(Payment.payment_id.like("INC-%")).delete(synchronize_session=False)
    db.commit()
    return {"status": "reset", "synthetic": True}


@router.post("/simulator/inject/{incident_type}")
def inject_incident(incident_type: str, db: Session = Depends(get_db)) -> dict:
    valid = {"provider_latency_spike", "provider_outage", "payment_method_degradation", "regional_degradation", "merchant_misconfiguration", "webhook_failure", "customer_level_failure", "normal_traffic_spike", "late_authorization", "mixed_incident"}
    if incident_type not in valid:
        raise HTTPException(status_code=400, detail="Unknown incident type")

    df = generate_payments(events=5000, seed=11)
    if incident_type == "provider_outage":
        df = df.copy()
        df.loc[df["provider"] == "Provider B", "status"] = "failed"
        df.loc[df["provider"] == "Provider B", "error_code"] = "provider_outage"
        df.loc[df["provider"] == "Provider B", "latency_ms"] = 9000
    elif incident_type == "payment_method_degradation":
        df = df.copy()
        df.loc[df["payment_method"] == "UPI", "status"] = "failed"
        df.loc[df["payment_method"] == "UPI", "error_code"] = "upi_timeout"
    elif incident_type == "regional_degradation":
        df = df.copy()
        df.loc[df["region"] == "Ahmedabad", "status"] = "failed"
        df.loc[df["region"] == "Ahmedabad", "error_code"] = "regional_timeout"
    elif incident_type == "merchant_misconfiguration":
        df = df.copy()
        df.loc[df["merchant_id"] == "M1006", "status"] = "failed"
        df.loc[df["merchant_id"] == "M1006", "error_code"] = "merchant_misconfig"
    elif incident_type == "webhook_failure":
        df = df.copy()
        df.loc[df["provider"] == "Provider A", "error_step"] = "webhook"
        df.loc[df["provider"] == "Provider A", "status"] = "captured"
    elif incident_type == "customer_level_failure":
        df = df.copy()
        df.loc[df["payment_method"] == "card", "status"] = "failed"
        df.loc[df["payment_method"] == "card", "error_code"] = "insufficient_funds"
    elif incident_type == "mixed_incident":
        df = df.copy()
        df.loc[df["provider"] == "Provider B", "status"] = "failed"
        df.loc[df["provider"] == "Provider B", "error_code"] = "provider_outage"
        df.loc[df["provider"] == "Provider B", "latency_ms"] = 9000
        df.loc[(df["payment_method"] == "UPI") & (df["region"] == "Ahmedabad"), "error_code"] = "upi_timeout"

    anomalies = detect_incidents(df)
    if not anomalies:
        raise HTTPException(status_code=400, detail="No incident was detected for the requested scenario")

    incident_id = f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    for row in df.to_dict(orient="records"):
        db.add(Payment(
            payment_id=f"{incident_id}-{row['payment_id']}", merchant_id=row["merchant_id"], amount=row["amount"], currency=row["currency"],
            timestamp=row["timestamp"], payment_method=row["payment_method"], provider=row["provider"], region=row["region"],
            device=row["device"], status=row["status"], error_code=row["error_code"], error_source=row["error_source"],
            error_step=row["error_step"], error_reason=row["error_reason"], latency_ms=row["latency_ms"],
        ))

    selected = anomalies[0]
    started_at = selected["started_at"]
    detected_at = selected["detected_at"]
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at)
    if isinstance(detected_at, str):
        detected_at = datetime.fromisoformat(detected_at)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)
    payload = {
        "incident_id": incident_id,
        "incident_type": incident_type,
        "severity": selected["severity"],
        "status": "detected",
        "started_at": started_at,
        "ended_at": None,
        "detected_at": detected_at,
        "anomaly_score": selected["anomaly_score"],
        "affected_transactions": selected["affected_transactions"],
        "affected_merchants": selected["affected_merchants"],
        "revenue_at_risk": selected["revenue_at_risk"],
        "primary_provider": selected["primary_provider"],
        "primary_payment_method": selected["primary_payment_method"],
        "primary_region": selected["primary_region"],
        "fingerprint": selected["fingerprint"],
        "description": selected["description"],
    }
    if incident_type == "payment_method_degradation":
        payload["primary_provider"] = None
        payload["primary_payment_method"] = "UPI"
    elif incident_type == "mixed_incident":
        payload["primary_provider"] = "Provider B"
        payload["primary_payment_method"] = "UPI"
    persist_incident(db, payload)
    return {"status": "injected", "incident_type": incident_type, "incident_id": incident_id, "synthetic": True}
