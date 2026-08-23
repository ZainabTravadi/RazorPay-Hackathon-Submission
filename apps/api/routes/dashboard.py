from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.services.incident_service import list_active_incidents
from database.models import Payment
from database.session import get_db
from ml.anomaly.detector import detect_anomalies
from data.generator.generate import generate_payments

router = APIRouter(prefix="/api")


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict:
    payments = db.query(Payment).all()
    if payments:
        total = len(payments)
        failed = sum(payment.status == "failed" for payment in payments)
        failure_rate = failed / total
        success_rate = sum(payment.status in {"captured", "authorized"} for payment in payments) / total
        anomalies = []
    else:
        df = generate_payments(events=5000, seed=42)
        anomalies = detect_anomalies(df)
        failure_rate = float((df["status"] == "failed").mean())
        success_rate = float(df["status"].isin(["captured", "authorized"]).mean())
    active_incidents = list_active_incidents(db)
    total_failed = sum(payment.status == "failed" for payment in payments)
    revenue_total = sum(float(payment.amount) for payment in payments if payment.status == "failed")
    return {
        "payment_success_rate": round(success_rate, 4),
        "failure_rate": round(failure_rate, 4),
        "revenue_at_risk": round(revenue_total * 0.18, 2),
        "active_incidents": len(active_incidents) + len(anomalies),
        "synthetic": True,
        "failed_transactions": total_failed,
    }
