from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.schemas.recovery import ImpactAnalysis, PolicyDecision, RecoveryExecution, RecoveryRecommendation
from database.models import Incident, Payment, RecoveryExecutionRecord


def _incident(db: Session, incident_id: str) -> Incident:
    item = db.get(Incident, incident_id)
    if not item:
        raise ValueError("Incident not found")
    return item


def _payments(db: Session, item: Incident) -> list[Payment]:
    rows = db.scalars(select(Payment)).all()
    if item.primary_provider:
        rows = [row for row in rows if row.provider == item.primary_provider]
    if item.primary_payment_method:
        rows = [row for row in rows if row.payment_method == item.primary_payment_method]
    return rows


def calculate_impact(db: Session, incident_id: str) -> ImpactAnalysis:
    incident = _incident(db, incident_id); rows = _payments(db, incident)
    failed = [row for row in rows if row.status == "failed"]
    total = len(rows); failed_count = len(failed)
    duration = ((incident.ended_at or incident.detected_at) - incident.started_at).total_seconds() / 60
    recoverable = [row for row in failed if "timeout" in (row.error_code or "").lower() or "outage" in (row.error_code or "").lower()]
    return ImpactAnalysis(incident_id=incident_id, affected_transactions=total, affected_merchants=len({row.merchant_id for row in failed}),
        affected_payment_methods=sorted({row.payment_method for row in failed}), affected_providers=sorted({row.provider for row in failed}),
        failed_transactions=failed_count, affected_transaction_value=round(sum(row.amount for row in failed), 2),
        revenue_at_risk=round(sum(row.amount for row in failed) * .18, 2), estimated_recoverable_transactions=len(recoverable),
        estimated_recoverable_revenue=round(sum(row.amount for row in recoverable) * .18, 2), incident_duration_minutes=round(max(duration, 0), 2),
        baseline_success_rate=.94, degraded_success_rate=round((total - failed_count) / total, 4) if total else 0,
        success_rate_delta=round(((total - failed_count) / total if total else 0) - .94, 4))


def recommend_recovery(db: Session, incident_id: str) -> RecoveryRecommendation:
    incident = _incident(db, incident_id); impact = calculate_impact(db, incident_id)
    if incident.incident_type == "customer_level_failure":
        strategy = "no_action"; reason = "Customer-level declines are not safe for automated recovery."; risk = ["Retrying issuer declines may create customer friction."]
    elif incident.incident_type == "regional_degradation":
        strategy = "delayed_retry"; reason = "Regional degradation needs a bounded delayed retry after conditions stabilize."; risk = ["Regional conditions may remain unstable."]
    elif incident.primary_provider and ("provider" in incident.incident_type or incident.incident_type == "mixed_incident"):
        strategy = "provider_failover"; reason = "Provider-scoped degradation has timeout/outage evidence."; risk = ["Fallback provider capacity must be verified."]
    elif incident.primary_payment_method or "payment_method" in incident.incident_type:
        strategy = "alternative_method"; reason = "Failures are concentrated on a payment method."; risk = ["Customer conversion may decline on an alternate method."]
    elif impact.estimated_recoverable_transactions:
        strategy = "bounded_retry"; reason = "Transient timeout failures are eligible for an idempotent retry simulation."; risk = ["Duplicate payment risk requires idempotency."]
    else:
        strategy = "no_action"; reason = "No safe recoverable failure class was found."; risk = ["Insufficient evidence for automation."]
    return RecoveryRecommendation(incident_id=incident_id, strategy=strategy, reason=reason, expected_benefit="Recover eligible failed transactions in the sandbox.",
        estimated_recoverable_transactions=impact.estimated_recoverable_transactions, estimated_recoverable_revenue=impact.estimated_recoverable_revenue,
        confidence=.85 if strategy != "no_action" else .3, assumptions=["Synthetic data only", "Simulation does not mutate payments"], risks=risk)


def evaluate_policy(db: Session, incident_id: str) -> PolicyDecision:
    incident = _incident(db, incident_id); recommendation = recommend_recovery(db, incident_id)
    reasons: list[str] = []; blocked: list[str] = []
    if incident.severity == "critical": reasons.append("Critical incidents require an operator approval.")
    if recommendation.confidence < .7: blocked.append(recommendation.strategy); reasons.append("Confidence is below the automatic-action threshold.")
    if recommendation.strategy == "no_action": blocked.append("all_recovery")
    return PolicyDecision(allowed=not blocked, requires_human_approval=True, risk_level="high" if incident.severity == "critical" else "medium", reasons=reasons or ["Read-only policy checks passed."], blocked_actions=blocked)


def create_recovery(db: Session, incident_id: str) -> RecoveryExecution:
    recommendation = recommend_recovery(db, incident_id); policy = evaluate_policy(db, incident_id)
    if not policy.allowed: raise PermissionError("Recovery is blocked by policy")
    existing = db.scalars(select(RecoveryExecutionRecord).where(RecoveryExecutionRecord.incident_id == incident_id, RecoveryExecutionRecord.approval_status.in_(["pending", "approved"]))).first()
    if existing: raise ValueError("An active recovery already exists for this incident")
    now = datetime.now(timezone.utc); impact = calculate_impact(db, incident_id)
    result = RecoveryExecution(recovery_id=f"REC-{uuid.uuid4().hex[:10].upper()}", incident_id=incident_id, strategy=recommendation.strategy,
        approval_status="pending", execution_status="not_started", before_metrics=impact.model_dump(), timestamp=now)
    db.add(RecoveryExecutionRecord(recovery_id=result.recovery_id, incident_id=incident_id, strategy=result.strategy, approval_status="pending", execution_status="not_started", payload_json=result.model_dump_json(), timestamp=now)); db.commit()
    return result


def approve_and_simulate(db: Session, recovery_id: str) -> RecoveryExecution:
    row = db.get(RecoveryExecutionRecord, recovery_id)
    if not row: raise ValueError("Recovery not found")
    if row.approval_status != "pending": raise ValueError("Recovery is not awaiting approval")
    result = RecoveryExecution.model_validate_json(row.payload_json); result.approval_status = "approved"
    row.approval_status = "approved"; row.payload_json = result.model_dump_json(); db.commit()
    return result


def execute_simulation(db: Session, recovery_id: str) -> RecoveryExecution:
    row = db.get(RecoveryExecutionRecord, recovery_id)
    if not row: raise ValueError("Recovery not found")
    if row.approval_status != "approved": raise PermissionError("Recovery requires explicit approval")
    if row.execution_status != "not_started": raise ValueError("Recovery has already been executed")
    result = RecoveryExecution.model_validate_json(row.payload_json)
    impact = ImpactAnalysis.model_validate(result.before_metrics); recovered = impact.estimated_recoverable_transactions
    result.execution_status = "completed"; result.recovered_transactions = recovered; result.recovered_revenue = impact.estimated_recoverable_revenue
    result.recovery_rate = round(recovered / impact.failed_transactions, 4) if impact.failed_transactions else 0
    result.simulated_latency_impact_ms = 50; result.after_metrics = {"success_rate": round(impact.degraded_success_rate + (recovered / impact.affected_transactions if impact.affected_transactions else 0), 4), "recovered_transactions": recovered}
    row.execution_status = "completed"; row.payload_json = result.model_dump_json(); db.commit(); return result


def reject_recovery(db: Session, recovery_id: str) -> RecoveryExecution:
    row = db.get(RecoveryExecutionRecord, recovery_id)
    if not row: raise ValueError("Recovery not found")
    result = RecoveryExecution.model_validate_json(row.payload_json); result.approval_status = "rejected"; row.approval_status = "rejected"; row.payload_json = result.model_dump_json(); db.commit(); return result