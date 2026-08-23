from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from data.generator.generate import generate_payments
from database.models import Payment
from database.session import get_db

router = APIRouter(prefix="/api")


@router.get("/payments")
def list_payments(
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    records = db.query(Payment).order_by(Payment.timestamp.desc()).offset(offset).limit(limit).all()
    if records:
        page = [{"payment_id": row.payment_id, "merchant_id": row.merchant_id, "amount": row.amount, "currency": row.currency,
                 "timestamp": row.timestamp, "payment_method": row.payment_method, "provider": row.provider, "region": row.region,
                 "device": row.device, "status": row.status, "error_code": row.error_code, "error_source": row.error_source,
                 "error_step": row.error_step, "error_reason": row.error_reason, "latency_ms": row.latency_ms} for row in records]
    else:
        df = generate_payments(events=2000, seed=42)
        page = df.iloc[offset: offset + limit].to_dict(orient="records")
    return {"items": page, "count": len(page), "synthetic": True}
