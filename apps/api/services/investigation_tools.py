from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import HistoricalIncident, Incident, Payment
from ml.fingerprinting.fingerprint import fingerprint_similarity


def _incident(db: Session, incident_id: str) -> Incident:
    item = db.get(Incident, incident_id)
    if not item:
        raise ValueError("Incident not found")
    return item


def _rows(db: Session, item: Incident) -> list[Payment]:
    query = select(Payment)
    if item.primary_provider:
        query = query.where(Payment.provider == item.primary_provider)
    if item.primary_payment_method:
        query = query.where(Payment.payment_method == item.primary_payment_method)
    return db.scalars(query).all()


def get_incident_details(db: Session, incident_id: str) -> dict[str, Any]:
    item = _incident(db, incident_id)
    return {"incident_id": item.incident_id, "incident_type": item.incident_type, "severity": item.severity,
            "status": item.status, "started_at": item.started_at.isoformat(), "detected_at": item.detected_at.isoformat(),
            "anomaly_score": item.anomaly_score, "affected_transactions": item.affected_transactions,
            "affected_merchants": item.affected_merchants, "revenue_at_risk": item.revenue_at_risk,
            "provider": item.primary_provider, "payment_method": item.primary_payment_method, "region": item.primary_region,
            "fingerprint": item.fingerprint, "description": item.description}


def get_payment_metrics(db: Session, incident_id: str) -> dict[str, Any]:
    rows = _rows(db, _incident(db, incident_id))
    total = len(rows); failed = sum(row.status == "failed" for row in rows)
    return {"total_transactions": total, "failed_transactions": failed,
            "failure_rate": round(failed / total, 4) if total else 0,
            "success_rate": round(sum(row.status in {"captured", "authorized"} for row in rows) / total, 4) if total else 0,
            "average_latency_ms": round(sum(row.latency_ms for row in rows) / total, 2) if total else 0}


def get_provider_health(db: Session, provider_id: str) -> dict[str, Any]:
    rows = db.scalars(select(Payment).where(Payment.provider == provider_id)).all()
    if not rows:
        raise ValueError("Provider not found or has no payments")
    failures = sum(row.status == "failed" for row in rows) / len(rows)
    latency = sorted(row.latency_ms for row in rows)[int((len(rows) - 1) * .95)]
    return {"provider": provider_id, "health_status": "degraded" if failures > .2 or latency > 2000 else "healthy",
            "success_rate": round(1 - failures, 4), "failure_rate": round(failures, 4), "latency_p95_ms": latency,
            "baseline_success_rate": .94, "baseline_latency_p95_ms": 910,
            "anomaly_score": round(failures / .06 + latency / 910, 2)}


def get_failure_clusters(db: Session, incident_id: str) -> dict[str, Any]:
    rows = [row for row in _rows(db, _incident(db, incident_id)) if row.status == "failed"]
    counts = Counter((row.error_code or "unknown") for row in rows)
    return {"clusters": [{"error_code": code, "count": count, "share": round(count / len(rows), 4) if rows else 0}
                          for code, count in counts.most_common()], "total_failures": len(rows)}


def get_merchant_impact(db: Session, incident_id: str) -> dict[str, Any]:
    rows = _rows(db, _incident(db, incident_id))
    grouped = Counter(row.merchant_id for row in rows if row.status == "failed")
    return {"affected_merchants": len(grouped), "top_merchants": [{"merchant_id": key, "failed_transactions": value}
            for key, value in grouped.most_common(10)]}


def get_error_distribution(db: Session, incident_id: str) -> dict[str, int]:
    return {item["error_code"]: item["count"] for item in get_failure_clusters(db, incident_id)["clusters"]}


def get_historical_baseline(db: Session, incident_id: str) -> dict[str, Any]:
    metrics = get_payment_metrics(db, incident_id)
    return {"current": metrics, "baseline": {"failure_rate": .06, "success_rate": .94, "latency_p95_ms": 910},
            "failure_rate_delta": round(metrics["failure_rate"] - .06, 4)}


def search_incident_history(db: Session, incident_id: str) -> list[dict[str, Any]]:
    item = _incident(db, incident_id)
    records = db.scalars(select(HistoricalIncident)).all()
    ranked = sorted(records, key=lambda record: fingerprint_similarity(item.fingerprint or "", record.fingerprint), reverse=True)
    return [{"incident_id": record.incident_id,
             "similarity": round(fingerprint_similarity(item.fingerprint or "", record.fingerprint), 4),
             "root_cause": record.root_cause, "resolution": record.resolution, "recovery_rate": record.recovery_rate}
            for record in ranked[:5]]


def get_transaction_timeline(db: Session, incident_id: str) -> list[dict[str, Any]]:
    item = _incident(db, incident_id); start = item.started_at
    return [{"time": (start - timedelta(minutes=30)).isoformat(), "event": "Baseline normal", "level": "info"},
            {"time": (start - timedelta(minutes=10)).isoformat(), "event": "Latency begins rising", "level": "warning"},
            {"time": item.detected_at.isoformat(), "event": "Incident detected", "level": "critical"},
            {"time": (item.detected_at + timedelta(minutes=5)).isoformat(), "event": "Peak degradation", "level": "critical"}]


def get_regional_metrics(db: Session, incident_id: str) -> dict[str, Any]:
    rows = _rows(db, _incident(db, incident_id)); values: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = values.setdefault(row.region, {"total": 0, "failed": 0})
        bucket["total"] += 1; bucket["failed"] += int(row.status == "failed")
    return {region: {**item, "failure_rate": round(item["failed"] / item["total"], 4)} for region, item in values.items()}


TOOLS: dict[str, Callable[..., Any]] = {
    "get_payment_metrics": get_payment_metrics, "get_provider_health": get_provider_health,
    "get_failure_clusters": get_failure_clusters, "get_merchant_impact": get_merchant_impact,
    "get_error_distribution": get_error_distribution, "get_historical_baseline": get_historical_baseline,
    "search_incident_history": search_incident_history, "get_transaction_timeline": get_transaction_timeline,
    "get_incident_details": get_incident_details, "get_regional_metrics": get_regional_metrics,
}


def call_tool(db: Session, name: str, **inputs: Any) -> Any:
    if name not in TOOLS:
        raise ValueError(f"Unknown read-only investigation tool: {name}")
    return TOOLS[name](db, **inputs)