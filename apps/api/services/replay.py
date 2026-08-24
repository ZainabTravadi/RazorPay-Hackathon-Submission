from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.schemas.investigation import Evidence, HistoricalMatch, Hypothesis, InvestigationResult
from apps.api.schemas.replay import ReplayEvent, ReplayIncidentSummary, ReplayPhase, ReplaySnapshot, ReplayTimeline
from apps.api.services.investigation_tools import (
    get_failure_clusters,
    get_historical_baseline,
    get_payment_metrics,
    get_provider_health,
    get_regional_metrics,
    search_incident_history,
)
from apps.api.services.investigator import evidence_confidence
from apps.api.services.recovery import calculate_impact, evaluate_policy, recommend_recovery
from database.models import HistoricalIncident, Incident, Investigation, RecoveryExecutionRecord


@dataclass(slots=True)
class _ReplaySubject:
    incident: ReplayIncidentSummary
    incident_row: Incident | None
    historical_row: HistoricalIncident | None
    investigation_row: Investigation | None
    investigation_result: InvestigationResult | None
    recovery_row: RecoveryExecutionRecord | None
    impact: dict[str, Any]
    recommendation: dict[str, Any]
    policy: dict[str, Any]
    projection: dict[str, Any]


def _normalize_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _shift(value: datetime, seconds: int) -> datetime:
    return _normalize_datetime(value) + timedelta(seconds=seconds)


def _event_id(incident_id: str, index: int, event_type: str) -> str:
    return f"RPL-{incident_id}-{index:02d}-{event_type.lower()}"


def _latest_row(db: Session, model: Any, incident_id: str, order_column: Any) -> Any | None:
    return db.scalars(select(model).where(model.incident_id == incident_id).order_by(order_column.desc())).first()


def _build_incident_summary(incident: Incident) -> ReplayIncidentSummary:
    return ReplayIncidentSummary(
        incident_id=incident.incident_id,
        source_kind="incident",
        incident_type=incident.incident_type,
        severity=incident.severity,
        status=incident.status,
        anomaly_score=incident.anomaly_score,
        started_at=_normalize_datetime(incident.started_at),
        detected_at=_normalize_datetime(incident.detected_at),
        ended_at=_normalize_datetime(incident.ended_at) if incident.ended_at else None,
        primary_provider=incident.primary_provider,
        primary_payment_method=incident.primary_payment_method,
        primary_region=incident.primary_region,
        description=incident.description,
        fingerprint=incident.fingerprint,
    )


def _build_historical_summary(historical: HistoricalIncident) -> ReplayIncidentSummary:
    started_at = _shift(historical.timestamp, -8 * 60)
    return ReplayIncidentSummary(
        incident_id=historical.incident_id,
        source_kind="historical",
        incident_type=historical.incident_type,
        severity="medium",
        status="resolved",
        anomaly_score=None,
        started_at=started_at,
        detected_at=_shift(historical.timestamp, -5 * 60),
        ended_at=_normalize_datetime(historical.timestamp),
        description=historical.root_cause,
        fingerprint=historical.fingerprint,
    )


def _historical_impact(summary: ReplayIncidentSummary, historical: HistoricalIncident) -> dict[str, Any]:
    return {
        "incident_id": summary.incident_id,
        "affected_transactions": 0,
        "affected_merchants": 0,
        "affected_payment_methods": [summary.primary_payment_method] if summary.primary_payment_method else [],
        "affected_providers": [summary.primary_provider] if summary.primary_provider else [],
        "failed_transactions": 0,
        "affected_transaction_value": round(historical.revenue_impact / 0.18, 2) if historical.revenue_impact else 0,
        "revenue_at_risk": round(historical.revenue_impact, 2),
        "estimated_recoverable_transactions": 0,
        "estimated_recoverable_revenue": 0,
        "incident_duration_minutes": 8.0,
        "baseline_success_rate": 0.94,
        "degraded_success_rate": 1 - min(max(historical.recovery_rate, 0), 1),
        "success_rate_delta": round((1 - min(max(historical.recovery_rate, 0), 1)) - 0.94, 4),
    }


def _historical_recommendation(summary: ReplayIncidentSummary, historical: HistoricalIncident, impact: dict[str, Any]) -> dict[str, Any]:
    if "provider" in historical.root_cause.lower():
        strategy = "provider_failover"
        reason = "Historical evidence points to provider degradation."
        confidence = 0.84
    elif "regional" in historical.root_cause.lower():
        strategy = "delayed_retry"
        reason = "Historical evidence points to regional instability."
        confidence = 0.76
    else:
        strategy = "no_action"
        reason = "Historical replay does not justify an automated recovery."
        confidence = 0.42
    return {
        "incident_id": summary.incident_id,
        "strategy": strategy,
        "reason": reason,
        "expected_benefit": "Review historical recovery posture against the replayed incident.",
        "estimated_recoverable_transactions": impact["estimated_recoverable_transactions"],
        "estimated_recoverable_revenue": impact["estimated_recoverable_revenue"],
        "confidence": confidence,
        "assumptions": ["Historical incident replay is read-only", "No live recovery mutation is performed"],
        "risks": ["Historical replay may not include granular telemetry"],
    }


def _project_investigation_live(db: Session, incident: Incident) -> dict[str, Any]:
    metrics = get_payment_metrics(db, incident.incident_id)
    clusters = get_failure_clusters(db, incident.incident_id)
    baseline = get_historical_baseline(db, incident.incident_id)
    regions = get_regional_metrics(db, incident.incident_id)
    history = search_incident_history(db, incident.incident_id)

    provider_health = {"health_status": "unknown", "latency_p95_ms": baseline["baseline"]["latency_p95_ms"]}
    if incident.primary_provider:
        try:
            provider_health = get_provider_health(db, incident.primary_provider)
        except ValueError:
            provider_health = {"health_status": "unknown", "latency_p95_ms": baseline["baseline"]["latency_p95_ms"]}

    dominant = clusters["clusters"][0] if clusters.get("clusters") else {}
    provider_supported = provider_health.get("health_status") == "degraded"
    region_rates = [item.get("failure_rate", 0) for item in regions.values()]
    regional = len(region_rates) == 1 or (region_rates and max(region_rates) - min(region_rates) > 0.15)
    best = history[0]["similarity"] if history else 0

    if incident.incident_type == "regional_degradation":
        root = f"{incident.primary_region or 'Regional'} infrastructure degradation"
        category = "regional_degradation"
    elif incident.incident_type == "customer_level_failure":
        root = "Customer-level payment failures"
        category = "customer_level_failure"
    elif incident.incident_type == "payment_method_degradation":
        root = f"{incident.primary_payment_method or 'Payment method'} failure concentration"
        category = "payment_method_degradation"
    else:
        root = f"{incident.primary_provider or 'Provider'} timeout degradation" if provider_supported else f"{dominant.get('error_code', 'payment')} failure concentration"
        category = "provider_degradation" if provider_supported else "payment_method_degradation"

    evidence = [
        Evidence(
            evidence_id="EV-001",
            source="payment_metrics",
            metric="failure_rate",
            observed_value=metrics["failure_rate"],
            baseline_value=baseline["baseline"]["failure_rate"],
            delta=baseline["failure_rate_delta"],
            severity="critical" if metrics["failure_rate"] > 0.25 else "high",
            relevance=0.95,
            description=f"Failure rate is {metrics['failure_rate']:.1%} versus {baseline['baseline']['failure_rate']:.1%} baseline",
        ),
        Evidence(
            evidence_id="EV-002",
            source="failure_clusters",
            metric="dominant_error_share",
            observed_value=dominant.get("share", 0),
            severity="high",
            relevance=0.88,
            description=f"{dominant.get('error_code', 'unknown')} is the dominant failure pattern",
        ),
        Evidence(
            evidence_id="EV-003",
            source="provider_health",
            metric="latency_p95_ms",
            observed_value=provider_health.get("latency_p95_ms", 0),
            baseline_value=baseline["baseline"]["latency_p95_ms"],
            delta=provider_health.get("latency_p95_ms", 0) - baseline["baseline"]["latency_p95_ms"],
            severity="critical" if provider_supported else "medium",
            relevance=0.94,
            description=f"Provider health is {provider_health.get('health_status')} with p95 latency {provider_health.get('latency_p95_ms', 0)}ms",
        ),
    ]
    hypotheses = [
        Hypothesis(
            hypothesis="Provider degradation",
            status="supported" if provider_supported else "partially_supported",
            reason="Provider health and failure metrics agree",
        ),
        Hypothesis(
            hypothesis="Payment-method-wide degradation",
            status="partially_supported" if not provider_supported else "rejected",
            reason="Error pattern is not isolated to the method" if provider_supported else "Method-level evidence remains plausible",
        ),
        Hypothesis(
            hypothesis="Regional infrastructure issue",
            status="partially_supported" if regional else "rejected",
            reason="Regional rates differ materially" if regional else "Impact is distributed across regions",
        ),
    ]

    confidence = evidence_confidence(
        incident.anomaly_score,
        len(evidence),
        0.9 if provider_supported else 0.65,
        best,
        0.1 if regional else 0,
    )
    return {
        "incident_id": incident.incident_id,
        "incident_summary": incident.description or "Detected payment incident",
        "root_cause": root,
        "root_cause_category": category,
        "confidence": confidence,
        "evidence": evidence,
        "alternative_hypotheses": hypotheses,
        "rejected_hypotheses": [item for item in hypotheses if item.status == "rejected"],
        "impact": {
            "revenue_at_risk": incident.revenue_at_risk,
            "affected_transactions": incident.affected_transactions,
            "affected_merchants": incident.affected_merchants,
        },
        "historical_matches": [HistoricalMatch(**item) for item in history],
        "recommended_next_step": "Evaluate alternate provider routing" if provider_supported else "Review payment-method operations",
        "investigation_duration": 0.0,
        "tool_call_count": 0,
        "provider_supported": provider_supported,
        "regional": regional,
    }


def _project_investigation_historical(historical: HistoricalIncident, summary: ReplayIncidentSummary) -> dict[str, Any]:
    provider_supported = "provider" in historical.root_cause.lower()
    regional = "regional" in historical.root_cause.lower()
    root = historical.root_cause
    confidence = min(max(0.6 + historical.recovery_rate * 0.3, 0.55), 0.97)
    evidence = [
        Evidence(
            evidence_id="EV-H001",
            source="historical_incident",
            metric="recovery_rate",
            observed_value=historical.recovery_rate,
            severity="high" if historical.recovery_rate < 0.85 else "medium",
            relevance=0.92,
            description=f"Historical recovery rate recorded at {historical.recovery_rate:.1%}",
        ),
    ]
    hypotheses = [
        Hypothesis(
            hypothesis=root,
            status="supported",
            reason="Historical record identifies this as the primary outcome",
        ),
        Hypothesis(
            hypothesis="Operational follow-up required",
            status="partially_supported" if not provider_supported else "supported",
            reason="Replay is limited to historical summary data",
        ),
        Hypothesis(
            hypothesis="Regional instability",
            status="partially_supported" if regional else "rejected",
            reason="Historical replay indicates a broader or narrower blast radius",
        ),
    ]
    return {
        "incident_id": summary.incident_id,
        "incident_summary": historical.resolution,
        "root_cause": root,
        "root_cause_category": "historical",
        "confidence": confidence,
        "evidence": evidence,
        "alternative_hypotheses": hypotheses,
        "rejected_hypotheses": [item for item in hypotheses if item.status == "rejected"],
        "impact": {"revenue_at_risk": historical.revenue_impact, "affected_transactions": 0, "affected_merchants": 0},
        "historical_matches": [],
        "recommended_next_step": "Review historical resolution and compare against replayed sequence",
        "investigation_duration": 0.0,
        "tool_call_count": 0,
        "provider_supported": provider_supported,
        "regional": regional,
    }


def _snapshot(state: dict[str, Any]) -> ReplaySnapshot:
    return ReplaySnapshot.model_validate(deepcopy(state))


def _subject_for_incident(db: Session, incident_id: str) -> _ReplaySubject:
    incident = db.get(Incident, incident_id)
    historical = None
    if incident is None:
        historical = db.get(HistoricalIncident, incident_id)
        if historical is None:
            raise ValueError("Incident not found")

    if incident is not None:
        investigation_row = _latest_row(db, Investigation, incident_id, Investigation.started_at)
        recovery_row = _latest_row(db, RecoveryExecutionRecord, incident_id, RecoveryExecutionRecord.timestamp)
        impact = calculate_impact(db, incident_id)
        recommendation = recommend_recovery(db, incident_id).model_dump(mode="json")
        policy = evaluate_policy(db, incident_id).model_dump(mode="json")
        investigation_result: InvestigationResult | None = None
        if investigation_row:
            try:
                investigation_result = InvestigationResult.model_validate_json(investigation_row.result_json)
            except Exception:
                investigation_result = None
        projected = investigation_result or InvestigationResult.model_validate(_project_investigation_live(db, incident))
        return _ReplaySubject(
            incident=_build_incident_summary(incident),
            incident_row=incident,
            historical_row=None,
            investigation_row=investigation_row,
            investigation_result=projected,
            recovery_row=recovery_row,
            impact=impact.model_dump(mode="json"),
            recommendation=recommendation,
            policy=policy,
            projection=projected.model_dump(mode="json"),
        )

    summary = _build_historical_summary(historical)  # type: ignore[arg-type]
    impact = _historical_impact(summary, historical)  # type: ignore[arg-type]
    recommendation = _historical_recommendation(summary, historical, impact)  # type: ignore[arg-type]
    policy = {
        "allowed": recommendation["strategy"] != "no_action",
        "requires_human_approval": True,
        "risk_level": "medium" if recommendation["strategy"] != "no_action" else "low",
        "reasons": ["Historical replay is read-only"],
        "blocked_actions": [] if recommendation["strategy"] != "no_action" else ["all_recovery"],
    }
    return _ReplaySubject(
        incident=summary,
        incident_row=None,
        historical_row=historical,
        investigation_row=None,
        investigation_result=InvestigationResult.model_validate(_project_investigation_historical(historical, summary)),
        recovery_row=None,
        impact=impact,
        recommendation=recommendation,
        policy=policy,
        projection=_project_investigation_historical(historical, summary),
    )


def _event(
    *,
    subject: _ReplaySubject,
    index: int,
    event_type: str,
    timestamp: datetime,
    title: str,
    description: str,
    phase: ReplayPhase,
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
    investigation_id: str | None = None,
    recovery_id: str | None = None,
    state: dict[str, Any],
) -> ReplayEvent:
    return ReplayEvent(
        event_id=_event_id(subject.incident.incident_id, index, event_type),
        index=index,
        type=event_type,
        timestamp=_normalize_datetime(timestamp),
        title=title,
        description=description,
        phase=phase,
        severity=severity,  # type: ignore[arg-type]
        incident_id=subject.incident.incident_id,
        investigation_id=investigation_id,
        recovery_id=recovery_id,
        snapshot=_snapshot(state),
        metadata=metadata or {},
    )


def _build_timeline(subject: _ReplaySubject) -> list[ReplayEvent]:
    events: list[ReplayEvent] = []
    state: dict[str, Any] = {
        "phase": "before_incident",
        "signal_summary": "Baseline traffic",
        "failure_rate": 0.06,
        "success_rate": 0.94,
        "provider_latency_p95_ms": 910,
        "affected_transactions": subject.impact.get("affected_transactions"),
        "affected_merchants": subject.impact.get("affected_merchants"),
        "revenue_at_risk": subject.impact.get("revenue_at_risk"),
        "confidence": None,
        "evidence_count": 0,
        "root_cause": None,
        "recommendation": None,
        "approval_status": None,
        "execution_status": None,
        "investigation_id": None,
        "recovery_id": None,
        "incident_status": subject.incident.status,
        "metrics": {
            "baseline_failure_rate": 0.06,
            "baseline_success_rate": 0.94,
            "baseline_latency_p95_ms": 910,
            "current_failure_rate": 0.06,
            "current_success_rate": 0.94,
        },
        "impact": subject.impact,
        "evidence": [],
        "hypotheses": [],
        "historical_matches": [],
    }

    incident = subject.incident
    started_at = _normalize_datetime(incident.started_at)
    detected_at = _normalize_datetime(incident.detected_at or _shift(started_at, 90))
    investigation = subject.investigation_row
    investigation_result = subject.investigation_result
    recovery = subject.recovery_row
    recovery_record = recovery
    recovery_timestamp = _normalize_datetime(recovery.timestamp) if recovery else None

    index = 1
    events.append(
        _event(
            subject=subject,
            index=index,
            event_type="INCIDENT_STARTED",
            timestamp=started_at,
            title="Incident starts",
            description="Persistent traffic enters the degraded window.",
            phase="before_incident",
            severity="info",
            metadata={"incident_id": incident.incident_id},
            state=state,
        )
    )

    index += 1
    state.update(
        {
            "phase": "detection",
            "signal_summary": "Detector flags anomalous payment behavior",
            "failure_rate": 0.14,
            "success_rate": 0.86,
            "provider_latency_p95_ms": 1800 if incident.primary_provider else 950,
            "metrics": {
                **state["metrics"],
                "current_failure_rate": 0.14,
                "current_success_rate": 0.86,
                "current_latency_p95_ms": 1800 if incident.primary_provider else 950,
            },
        }
    )
    events.append(
        _event(
            subject=subject,
            index=index,
            event_type="SIGNAL_DETECTED",
            timestamp=detected_at,
            title="Signal detected",
            description="The anomaly detector begins surfacing a potential incident.",
            phase="detection",
            severity="medium",
            metadata={"anomaly_score": incident.anomaly_score, "incident_id": incident.incident_id},
            state=state,
        )
    )

    index += 1
    state.update(
        {
            "signal_summary": "Failure rate diverges from baseline",
            "failure_rate": subject.impact.get("failed_transactions", 0) / max(subject.impact.get("affected_transactions", 1), 1) if subject.impact else 0.0,
            "success_rate": subject.impact.get("degraded_success_rate", 0.86),
            "provider_latency_p95_ms": 2800 if incident.primary_provider else 1200,
            "metrics": {
                **state["metrics"],
                "current_failure_rate": subject.impact.get("failed_transactions", 0) / max(subject.impact.get("affected_transactions", 1), 1) if subject.impact else 0.0,
                "current_success_rate": subject.impact.get("degraded_success_rate", 0.86),
                "current_latency_p95_ms": 2800 if incident.primary_provider else 1200,
            },
        }
    )
    events.append(
        _event(
            subject=subject,
            index=index,
            event_type="METRIC_ANOMALY",
            timestamp=_shift(detected_at, 14),
            title="Metric anomaly",
            description="Failure rate and latency move away from baseline in a correlated way.",
            phase="detection",
            severity="high",
            metadata={"baseline_failure_rate": 0.06, "failure_rate": state["failure_rate"]},
            state=state,
        )
    )

    index += 1
    state.update({"signal_summary": "Payment failures spike across the affected scope"})
    events.append(
        _event(
            subject=subject,
            index=index,
            event_type="PAYMENT_FAILURE_SPIKE",
            timestamp=_shift(detected_at, 28),
            title="Payment failure spike",
            description="Failed payments cluster around the degraded provider or method.",
            phase="detection",
            severity="critical",
            metadata={"incident_id": incident.incident_id, "affected_transactions": subject.impact.get("failed_transactions")},
            state=state,
        )
    )

    if incident.primary_provider:
        index += 1
        state.update({"signal_summary": f"{incident.primary_provider} degradation becomes visible", "provider_latency_p95_ms": 4200})
        events.append(
            _event(
                subject=subject,
                index=index,
                event_type="PROVIDER_DEGRADATION",
                timestamp=_shift(detected_at, 42),
                title="Provider degradation",
                description=f"{incident.primary_provider} is showing degraded health signals.",
                phase="detection",
                severity="critical",
                metadata={"provider": incident.primary_provider},
                state=state,
            )
        )
    elif incident.primary_region:
        index += 1
        state.update({"signal_summary": f"{incident.primary_region} shows concentrated impact"})
        events.append(
            _event(
                subject=subject,
                index=index,
                event_type="REGIONAL_IMPACT",
                timestamp=_shift(detected_at, 42),
                title="Regional impact",
                description=f"{incident.primary_region} carries a disproportionate share of the failures.",
                phase="detection",
                severity="high",
                metadata={"region": incident.primary_region},
                state=state,
            )
        )

    investigation_snapshot = investigation_result
    if investigation or investigation_snapshot:
        inv_id = investigation.investigation_id if investigation else None
        inv_start = _normalize_datetime(investigation.started_at) if investigation else _shift(detected_at, 74)
        index += 1
        state.update(
            {
                "phase": "investigation",
                "signal_summary": "Investigation begins",
                "investigation_id": inv_id,
                "evidence_count": len(investigation_snapshot.evidence) if investigation_snapshot else 0,
                "confidence": investigation_snapshot.confidence if investigation_snapshot else None,
                "root_cause": None,
                "metrics": {
                    **state["metrics"],
                    "evidence_count": len(investigation_snapshot.evidence) if investigation_snapshot else 0,
                },
            }
        )
        events.append(
            _event(
                subject=subject,
                index=index,
                event_type="INVESTIGATION_STARTED",
                timestamp=inv_start,
                title="Investigation starts",
                description="The investigation agent begins correlating payment signals.",
                phase="investigation",
                severity="info",
                investigation_id=inv_id,
                metadata={"incident_id": incident.incident_id},
                state=state,
            )
        )

        if investigation_snapshot and investigation_snapshot.alternative_hypotheses:
            index += 1
            top_hypothesis = investigation_snapshot.alternative_hypotheses[0]
            state.update(
                {
                    "signal_summary": "Hypotheses are ranked",
                    "hypotheses": investigation_snapshot.alternative_hypotheses,
                    "metrics": {
                        **state["metrics"],
                        "hypothesis_count": len(investigation_snapshot.alternative_hypotheses),
                    },
                }
            )
            events.append(
                _event(
                    subject=subject,
                    index=index,
                    event_type="HYPOTHESIS_CREATED",
                    timestamp=_shift(inv_start, 28),
                    title="Hypothesis created",
                    description=f"{top_hypothesis.hypothesis} becomes the leading hypothesis.",
                    phase="investigation",
                    severity="info",
                    investigation_id=inv_id,
                    metadata={"top_hypothesis": top_hypothesis.hypothesis},
                    state=state,
                )
            )

        for item_index, evidence in enumerate((investigation_snapshot.evidence if investigation_snapshot else [])[:3], start=1):
            index += 1
            state.update(
                {
                    "signal_summary": f"Evidence #{item_index} supports the active hypothesis",
                    "evidence": (investigation_snapshot.evidence if investigation_snapshot else [])[:item_index],
                    "evidence_count": item_index,
                    "metrics": {
                        **state["metrics"],
                        "evidence_count": item_index,
                    },
                }
            )
            events.append(
                _event(
                    subject=subject,
                    index=index,
                    event_type="EVIDENCE_DISCOVERED",
                    timestamp=_shift(inv_start, 44 + item_index * 16),
                    title=f"Evidence {item_index}",
                    description=evidence.description,
                    phase="investigation",
                    severity="high" if getattr(evidence, "severity", "medium") in {"high", "critical"} else "info",
                    investigation_id=inv_id,
                    metadata={"evidence_id": evidence.evidence_id, "source": evidence.source},
                    state=state,
                )
            )

        index += 1
        state.update(
            {
                "phase": "root_cause",
                "signal_summary": investigation_snapshot.root_cause if investigation_snapshot else "Root cause confirmed",
                "confidence": investigation_snapshot.confidence if investigation_snapshot else None,
                "root_cause": investigation_snapshot.root_cause if investigation_snapshot else None,
                "historical_matches": investigation_snapshot.historical_matches if investigation_snapshot else [],
                "metrics": {
                    **state["metrics"],
                    "confidence": investigation_snapshot.confidence if investigation_snapshot else None,
                },
            }
        )
        events.append(
            _event(
                subject=subject,
                index=index,
                event_type="RCA_CONFIRMED",
                timestamp=_shift(inv_start, 130 if not investigation or not getattr(investigation, "completed_at", None) else 0),
                title="Root cause confirmed",
                description=investigation_snapshot.incident_summary if investigation_snapshot else "The investigation reaches a stable conclusion.",
                phase="root_cause",
                severity="critical",
                investigation_id=inv_id,
                metadata={"confidence": investigation_snapshot.confidence if investigation_snapshot else None},
                state=state,
            )
        )
    else:
        state.update(
            {
                "phase": "root_cause",
                "signal_summary": "Limited replay available without investigation data",
                "root_cause": subject.incident.description or subject.recommendation.get("reason"),
                "confidence": subject.recommendation.get("confidence"),
                "metrics": {
                    **state["metrics"],
                    "confidence": subject.recommendation.get("confidence"),
                },
            }
        )
        index += 1
        events.append(
            _event(
                subject=subject,
                index=index,
                event_type="RCA_CONFIRMED",
                timestamp=_shift(detected_at, 120),
                title="RCA projection",
                description=subject.recommendation.get("reason", "Historical replay projects a likely root cause."),
                phase="root_cause",
                severity="high",
                metadata={"projection": True},
                state=state,
            )
        )

    index += 1
    state.update(
        {
            "phase": "recovery",
            "signal_summary": "Recovery is recommended",
            "recommendation": subject.recommendation.get("strategy"),
            "approval_status": None if recovery_record is None else recovery_record.approval_status,
            "execution_status": None if recovery_record is None else recovery_record.execution_status,
            "recovery_id": recovery_record.recovery_id if recovery_record else None,
            "metrics": {
                **state["metrics"],
                "recovery_confidence": subject.recommendation.get("confidence"),
            },
        }
    )
    recovery_recommended_at = _shift(detected_at, 150 if investigation is None else 160)
    events.append(
        _event(
            subject=subject,
            index=index,
            event_type="RECOVERY_RECOMMENDED",
            timestamp=recovery_recommended_at,
            title="Recovery recommended",
            description=subject.recommendation.get("reason", "A controlled recovery is available."),
            phase="recovery",
            severity="info",
            recovery_id=recovery_record.recovery_id if recovery_record else None,
            metadata={"strategy": subject.recommendation.get("strategy")},
            state=state,
        )
    )

    if recovery_record is not None:
        index += 1
        state.update(
            {
                "phase": "recovery",
                "approval_status": recovery_record.approval_status,
                "execution_status": recovery_record.execution_status,
                "recovery_id": recovery_record.recovery_id,
                "signal_summary": f"Recovery is {recovery_record.approval_status}",
            }
        )
        events.append(
            _event(
                subject=subject,
                index=index,
                event_type="RECOVERY_PREPARED",
                timestamp=recovery_timestamp or _shift(recovery_recommended_at, 20),
                title="Recovery prepared",
                description="Recovery has been staged as a controlled operation.",
                phase="recovery",
                severity="info",
                recovery_id=recovery_record.recovery_id,
                metadata={"timestamp": recovery_record.timestamp.isoformat()},
                state=state,
            )
        )

        if recovery_record.approval_status == "approved":
            index += 1
            state.update({"approval_status": recovery_record.approval_status})
            events.append(
                _event(
                    subject=subject,
                    index=index,
                    event_type="RECOVERY_APPROVED",
                    timestamp=_shift(recovery_timestamp or recovery_recommended_at, 18),
                    title="Human approval",
                    description="The backend policy gate records the recovery approval state.",
                    phase="recovery",
                    severity="info",
                    recovery_id=recovery_record.recovery_id,
                    metadata={"approval_status": recovery_record.approval_status},
                    state=state,
                )
            )

        if recovery_record.execution_status == "completed":
            index += 1
            state.update({"execution_status": "completed", "phase": "resolution", "signal_summary": "System stabilizes"})
            events.append(
                _event(
                    subject=subject,
                    index=index,
                    event_type="RECOVERY_EXECUTED",
                    timestamp=_shift(recovery_timestamp or recovery_recommended_at, 44),
                    title="Recovery executed",
                    description="The controlled simulation completed successfully.",
                    phase="resolution",
                    severity="info",
                    recovery_id=recovery_record.recovery_id,
                    metadata={"recovered_transactions": getattr(recovery_record, "recovered_transactions", 0)},
                    state=state,
                )
            )

            index += 1
            state.update({"phase": "resolution", "signal_summary": "Incident resolved"})
            events.append(
                _event(
                    subject=subject,
                    index=index,
                    event_type="INCIDENT_RESOLVED",
                    timestamp=_shift(recovery_timestamp or recovery_recommended_at, 74),
                    title="Incident resolved",
                    description="Payments stabilize after the simulated recovery completes.",
                    phase="resolution",
                    severity="info",
                    recovery_id=recovery_record.recovery_id,
                    metadata={"recovered_revenue": getattr(recovery_record, "recovered_revenue", 0)},
                    state=state,
                )
            )
    else:
        state.update({"phase": "recovery"})

    if incident.ended_at:
        end_at = _normalize_datetime(incident.ended_at)
    elif events:
        end_at = events[-1].timestamp
    else:
        end_at = _shift(started_at, 180)

    events.sort(key=lambda item: (item.timestamp, item.index))
    return events


def build_replay(db: Session, incident_id: str) -> ReplayTimeline:
    subject = _subject_for_incident(db, incident_id)
    events = _build_timeline(subject)
    if not events:
        raise ValueError("No replay data available for this incident")

    start_at = events[0].timestamp
    end_at = events[-1].timestamp
    current_phase = events[-1].phase
    has_investigation = any(event.type.startswith("INVESTIGATION") or event.type.startswith("HYPOTHESIS") or event.type.startswith("EVIDENCE") or event.type == "RCA_CONFIRMED" for event in events)
    has_recovery = any(event.type.startswith("RECOVERY") for event in events)
    return ReplayTimeline(
        incident=subject.incident,
        start_at=start_at,
        end_at=end_at,
        duration_seconds=max((end_at - start_at).total_seconds(), 0),
        event_count=len(events),
        replayable=True,
        deterministic=True,
        has_investigation=has_investigation,
        has_recovery=has_recovery,
        current_phase=current_phase,
        events=events,
    )


def build_replay_event(db: Session, incident_id: str, event_id: str) -> ReplayEvent:
    replay = build_replay(db, incident_id)
    for event in replay.events:
        if event.event_id == event_id:
            return event
    raise ValueError("Replay event not found")
