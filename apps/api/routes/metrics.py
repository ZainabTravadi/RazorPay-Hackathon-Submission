from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from data.generator.generate import generate_payments
from database.models import Payment
from database.session import get_db

router = APIRouter(prefix="/api")


def _summary_metrics(db: Session) -> dict:
    payments = db.query(Payment).all()
    if payments:
        total = len(payments)
        success_rate = sum(payment.status in {"captured", "authorized"} for payment in payments) / total
        failure_rate = sum(payment.status == "failed" for payment in payments) / total
        latency = sum(payment.latency_ms for payment in payments) / total
    else:
        df = generate_payments(events=5000, seed=42)
        success_rate = float(df["status"].isin(["captured", "authorized"]).mean())
        failure_rate = float((df["status"] == "failed").mean())
        latency = float(df["latency_ms"].mean())
    return {
        "success_rate": round(success_rate, 4),
        "failure_rate": round(failure_rate, 4),
        "latency": round(latency, 2),
    }


@router.get("/metrics/success-rate")
def success_rate(db: Session = Depends(get_db)) -> dict:
    return _summary_metrics(db)


@router.get("/metrics/failure-rate")
def failure_rate(db: Session = Depends(get_db)) -> dict:
    return _summary_metrics(db)


@router.get("/metrics/latency")
def latency(db: Session = Depends(get_db)) -> dict:
    return _summary_metrics(db)
