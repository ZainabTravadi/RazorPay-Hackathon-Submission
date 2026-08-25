from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.schemas.recovery import ImpactAnalysis, PolicyDecision, RecoveryExecution, RecoveryExecutionRequest, RecoveryRecommendation
from database.models import Incident, Payment, RecoveryAttemptRecord, RecoveryEventRecord, RecoveryExecutionRecord


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


def _recovery_row(db: Session, recovery_id: str) -> RecoveryExecutionRecord:
    row = db.get(RecoveryExecutionRecord, recovery_id)
    if not row:
        raise ValueError("Recovery not found")
    return row


def _record_recovery_event(db: Session, recovery_id: str, incident_id: str, payment_id: str | None, event_type: str, reason: str | None = None, metadata: dict | None = None) -> RecoveryEventRecord:
    now = datetime.now(timezone.utc)
    event = RecoveryEventRecord(
        event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
        recovery_id=recovery_id,
        incident_id=incident_id,
        payment_id=payment_id,
        event_type=event_type,
        reason=reason,
        metadata_json=json.dumps(metadata or {}, default=str),
        timestamp=now,
    )
    db.add(event)
    return event


def _ensure_execution_history(db: Session, recovery_id: str, incident_id: str, payment_id: str, attempt_number: int, strategy: str, amount: float, recovered_amount: float, success: bool, failure_reason: str | None = None) -> RecoveryAttemptRecord:
    attempt = RecoveryAttemptRecord(
        attempt_id=f"ATT-{uuid.uuid4().hex[:12].upper()}",
        recovery_id=recovery_id,
        incident_id=incident_id,
        payment_id=payment_id,
        attempt_number=attempt_number,
        strategy=strategy,
        status="success" if success else "failed",
        success=success,
        amount=amount,
        recovered_amount=recovered_amount,
        failure_reason=failure_reason,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(attempt)
    return attempt


def _recovery_attempts(db: Session, recovery_id: str) -> list[dict]:
    rows = db.scalars(select(RecoveryAttemptRecord).where(RecoveryAttemptRecord.recovery_id == recovery_id).order_by(RecoveryAttemptRecord.attempt_number)).all()
    return [
        {
            "attempt_id": row.attempt_id,
            "recovery_id": row.recovery_id,
            "incident_id": row.incident_id,
            "payment_id": row.payment_id,
            "attempt_number": row.attempt_number,
            "strategy": row.strategy,
            "status": row.status,
            "success": row.success,
            "amount": row.amount,
            "recovered_amount": row.recovered_amount,
            "failure_reason": row.failure_reason,
            "timestamp": row.timestamp.isoformat(),
        }
        for row in rows
    ]


def _recovery_events(db: Session, recovery_id: str) -> list[dict]:
    rows = db.scalars(select(RecoveryEventRecord).where(RecoveryEventRecord.recovery_id == recovery_id).order_by(RecoveryEventRecord.timestamp)).all()
    return [
        {
            "event_id": row.event_id,
            "recovery_id": row.recovery_id,
            "incident_id": row.incident_id,
            "payment_id": row.payment_id,
            "event_type": row.event_type,
            "reason": row.reason,
            "metadata_json": json.loads(row.metadata_json or "{}"),
            "timestamp": row.timestamp.isoformat(),
        }
        for row in rows
    ]


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
        approval_status="pending", execution_status="not_started", before_metrics=impact.model_dump(), timestamp=now, status="pending")
    db.add(RecoveryExecutionRecord(recovery_id=result.recovery_id, incident_id=incident_id, strategy=result.strategy, status="pending", approval_status="pending", execution_status="not_started", payload_json=result.model_dump_json(), timestamp=now)); db.commit()
    _record_recovery_event(db, result.recovery_id, incident_id, None, "RECOVERY_PREPARED", reason="Recovery action prepared and staged for review.", metadata={"strategy": result.strategy})
    db.commit()
    return result


def approve_and_simulate(db: Session, recovery_id: str) -> RecoveryExecution:
    row = _recovery_row(db, recovery_id)
    if row.approval_status != "pending": raise ValueError("Recovery is not awaiting approval")
    result = RecoveryExecution.model_validate_json(row.payload_json); result.approval_status = "approved"; result.status = "approved"; result.execution_status = "not_started"
    row.approval_status = "approved"; row.status = "approved"; row.payload_json = result.model_dump_json();
    _record_recovery_event(db, recovery_id, row.incident_id, None, "RECOVERY_APPROVED", reason="Operator approval captured within policy guardrails.", metadata={"approval_status": "approved"})
    db.commit()
    return result


def _finish_stopped_recovery(
    db: Session,
    row: RecoveryExecutionRecord,
    result: RecoveryExecution,
    rule: str,
    reason: str,
    event_type: str = "STOPPING_RULE_TRIGGERED",
) -> RecoveryExecution:
    successful_attempts = db.scalars(
        select(RecoveryAttemptRecord)
        .where(RecoveryAttemptRecord.recovery_id == row.recovery_id, RecoveryAttemptRecord.success.is_(True))
    ).all()
    successful_payments = {attempt.payment_id: attempt for attempt in successful_attempts}
    result.recovered_transactions = len(successful_payments)
    result.recovered_revenue = round(sum(attempt.amount for attempt in successful_payments.values()) * 0.18, 2)
    result.recovery_rate = round(result.recovered_transactions / max(len(_payments(db, _incident(db, row.incident_id))), 1), 4)
    result.status = "escalated" if event_type == "RECOVERY_ESCALATED" else "blocked"
    result.execution_status = "escalated" if event_type == "RECOVERY_ESCALATED" else "blocked"
    result.stop_reason = reason
    result.triggering_rule = rule
    row.status = result.status
    row.execution_status = result.execution_status
    row.payload_json = result.model_dump_json()
    _record_recovery_event(db, row.recovery_id, row.incident_id, None, "STOPPING_RULE_TRIGGERED", reason=reason, metadata={"rule": rule, "stop_reason": reason})
    if event_type != "STOPPING_RULE_TRIGGERED":
        _record_recovery_event(db, row.recovery_id, row.incident_id, None, event_type, reason=reason, metadata={"rule": rule, "stop_reason": reason})
    db.commit()
    return result


def execute_simulation(db: Session, recovery_id: str, request: RecoveryExecutionRequest | None = None) -> RecoveryExecution:
    row = _recovery_row(db, recovery_id)
    if row.approval_status != "approved": raise PermissionError("Recovery requires explicit approval")
    if row.execution_status != "not_started": raise ValueError("Recovery has already been executed")

    result = RecoveryExecution.model_validate_json(row.payload_json)
    enforce_window = request is not None
    request = request or RecoveryExecutionRequest()
    result.max_retries = request.max_retries
    result.fallback_strategy = request.fallback_strategy
    result.failure_rate_threshold = request.failure_rate_threshold
    result.recovery_window_seconds = request.recovery_window_seconds
    result.stop_reason = None
    result.triggering_rule = None
    incident = _incident(db, row.incident_id)
    eligible = list({payment.payment_id: payment for payment in _payments(db, incident) if payment.status == "failed"}.values())
    policy = {"max_retries": request.max_retries, "fallback_strategy": request.fallback_strategy,
              "failure_rate_threshold": request.failure_rate_threshold, "recovery_window_seconds": request.recovery_window_seconds}
    result.before_metrics["execution_policy"] = policy
    row.payload_json = result.model_dump_json()

    elapsed = (datetime.now(timezone.utc) - incident.started_at.replace(tzinfo=timezone.utc)).total_seconds()
    if enforce_window and elapsed > request.recovery_window_seconds:
        return _finish_stopped_recovery(db, row, result, "RECOVERY_TIME_WINDOW", "Recovery window expired before execution.")
    if not eligible:
        result.status = "completed"
        result.execution_status = "completed"
        result.recovered_transactions = 0
        result.recovered_revenue = 0.0
        result.recovery_rate = 0.0
        result.after_metrics = {"success_rate": result.before_metrics.get("degraded_success_rate", 0), "recovered_transactions": 0}
        row.status = "completed"
        row.execution_status = "completed"
        row.payload_json = result.model_dump_json()
        _record_recovery_event(db, recovery_id, row.incident_id, None, "RECOVERY_EXECUTED", reason="No failed payments were eligible for automated rebound.", metadata={"recovered_transactions": 0, "recovered_revenue": 0.0})
        db.commit()
        return result

    result.status = "running"
    row.status = "running"
    row.execution_status = "running"
    row.payload_json = result.model_dump_json()
    db.commit()

    recovered_transactions = 0
    recovered_revenue = 0.0
    failed_payments = 0
    retry_exhausted = False
    primary_index = 0
    fallback_index = 0
    for payment in eligible:
        attempt_number = 1
        success = True
        strategy = result.strategy
        for retry_number in range(request.max_retries + 1):
            _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "ATTEMPT_STARTED", metadata={"attempt_number": attempt_number, "strategy": strategy})
            outcome = (request.primary_outcomes or ["success"])[primary_index] if request.primary_outcomes and primary_index < len(request.primary_outcomes) else "success"
            primary_index += 1
            success = outcome == "success"
            attempt = _ensure_execution_history(db, recovery_id, row.incident_id, payment.payment_id, attempt_number, strategy, payment.amount, payment.amount if success else 0.0, success, None if success else "Primary strategy failed")
            if success:
                break
            failed_payments += 1
            _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "ATTEMPT_FAILED", reason="Primary strategy failed.", metadata={"attempt_id": attempt.attempt_id, "attempt_number": attempt_number})
            if failed_payments / len(eligible) > request.failure_rate_threshold:
                return _finish_stopped_recovery(db, row, result, "FAILURE_RATE_THRESHOLD", "Failure rate exceeded configured threshold.")
            if retry_number < request.max_retries:
                attempt_number += 1
                _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "RETRY_TRIGGERED", reason="Retry budget remains available.", metadata={"attempt_number": attempt_number})

        if success:
            recovered_transactions += 1
            recovered_revenue += payment.amount
            _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "PAYMENT_RECOVERED", reason="Payment recovered by the primary strategy.", metadata={"amount": payment.amount, "recovered_amount": payment.amount, "attempt_id": attempt.attempt_id})
            continue

        if request.fallback_strategy:
            attempt_number += 1
            _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "FALLBACK_TRIGGERED", reason="Primary recovery attempts failed; fallback strategy selected.", metadata={"strategy": request.fallback_strategy})
            _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "ATTEMPT_STARTED", metadata={"attempt_number": attempt_number, "strategy": request.fallback_strategy})
            outcome = (request.fallback_outcomes or ["success"])[fallback_index] if request.fallback_outcomes and fallback_index < len(request.fallback_outcomes) else "success"
            fallback_index += 1
            fallback_success = outcome == "success"
            attempt = _ensure_execution_history(db, recovery_id, row.incident_id, payment.payment_id, attempt_number, request.fallback_strategy, payment.amount, payment.amount if fallback_success else 0.0, fallback_success, None if fallback_success else "Fallback strategy failed")
            if fallback_success:
                recovered_transactions += 1
                recovered_revenue += payment.amount
                _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "PAYMENT_RECOVERED", reason="Payment recovered by the fallback strategy.", metadata={"amount": payment.amount, "recovered_amount": payment.amount, "attempt_id": attempt.attempt_id})
                continue
            _record_recovery_event(db, recovery_id, row.incident_id, payment.payment_id, "ATTEMPT_FAILED", reason="Fallback strategy failed.", metadata={"attempt_id": attempt.attempt_id, "strategy": request.fallback_strategy})
            return _finish_stopped_recovery(db, row, result, "FALLBACK_FAILED", "Fallback strategy failed; human handling is required.", "RECOVERY_ESCALATED")

        retry_exhausted = True

    if retry_exhausted:
        return _finish_stopped_recovery(db, row, result, "MAX_RETRIES", "Retry budget exhausted and no fallback strategy is configured.", "RECOVERY_ESCALATED")

    if recovered_transactions:
        result.execution_status = "completed"; result.status = "completed"
        result.recovered_transactions = recovered_transactions
        result.recovered_revenue = round(recovered_revenue * 0.18, 2)
        result.recovery_rate = round(recovered_transactions / max(len(eligible), 1), 4)
        result.simulated_latency_impact_ms = 50
        result.after_metrics = {"success_rate": round(result.before_metrics.get("degraded_success_rate", 0) + (recovered_transactions / max(len(eligible), 1)), 4), "recovered_transactions": recovered_transactions}
        row.execution_status = "completed"; row.status = "completed"; row.payload_json = result.model_dump_json()
        _record_recovery_event(db, recovery_id, row.incident_id, None, "RECOVERY_EXECUTED", reason="Recovery simulation completed across the eligible payment ledger.", metadata={"recovered_transactions": recovered_transactions, "recovered_revenue": result.recovered_revenue})
    db.commit()
    return result


def reject_recovery(db: Session, recovery_id: str) -> RecoveryExecution:
    row = _recovery_row(db, recovery_id)
    result = RecoveryExecution.model_validate_json(row.payload_json); result.approval_status = "rejected"; result.status = "cancelled"; row.approval_status = "rejected"; row.status = "cancelled"; row.payload_json = result.model_dump_json();
    _record_recovery_event(db, recovery_id, row.incident_id, None, "RECOVERY_REJECTED", reason="Recovery was explicitly rejected and is now closed.", metadata={"approval_status": "rejected"})
    db.commit(); return result


def get_recovery_attempts(db: Session, recovery_id: str) -> list[dict]:
    _recovery_row(db, recovery_id)
    return _recovery_attempts(db, recovery_id)


def get_recovery_events(db: Session, recovery_id: str) -> list[dict]:
    _recovery_row(db, recovery_id)
    return _recovery_events(db, recovery_id)


def get_latest_recovery(db: Session, incident_id: str) -> RecoveryExecution:
    _incident(db, incident_id)
    row = db.scalars(
        select(RecoveryExecutionRecord)
        .where(RecoveryExecutionRecord.incident_id == incident_id)
        .order_by(RecoveryExecutionRecord.timestamp.desc(), RecoveryExecutionRecord.recovery_id.desc())
    ).first()
    if not row:
        raise ValueError("Recovery not found")
    return RecoveryExecution.model_validate_json(row.payload_json)