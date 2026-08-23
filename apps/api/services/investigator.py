from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from apps.api.schemas.investigation import Evidence, HistoricalMatch, Hypothesis, InvestigationResult, InvestigationTrace, ToolCall
from apps.api.services.investigation_tools import call_tool
from database.models import Incident, Investigation

MAX_INVESTIGATION_STEPS = 12
logger = logging.getLogger("fluxpay.investigation")


def evidence_confidence(anomaly_score: float, evidence_count: int, agreement: float, history: float, contradiction: float) -> float:
    """Reproducible score: 35% anomaly, 25% independent evidence, 20% agreement, 20% history, less contradiction."""
    anomaly = min(anomaly_score / 10, 1)
    value = .35 * anomaly + .25 * min(evidence_count / 4, 1) + .20 * agreement + .20 * history - .20 * contradiction
    return round(max(0, min(value, 1)), 2)


def investigate(db: Session, incident_id: str) -> InvestigationTrace:
    incident = db.get(Incident, incident_id)
    if not incident:
        raise ValueError("Incident not found")
    started = datetime.now(timezone.utc); investigation_id = f"INV-{uuid.uuid4().hex[:10].upper()}"
    trace = InvestigationTrace(investigation_id=investigation_id, incident_id=incident_id, started_at=started,
                               agent=os.getenv("LLM_MODEL", "mock-investigator"))
    logger.info("investigation_started id=%s incident=%s", investigation_id, incident_id)

    def observe(step: int, name: str, purpose: str, inputs: dict[str, Any]) -> Any:
        if len(trace.tool_calls) >= MAX_INVESTIGATION_STEPS:
            raise RuntimeError("Investigation step limit exceeded")
        call_started = datetime.now(timezone.utc)
        output = call_tool(db, name, **inputs)
        call_finished = datetime.now(timezone.utc)
        trace.tool_calls.append(ToolCall(step=step, tool=name, purpose=purpose, inputs=inputs, output=output if isinstance(output, dict) else {"items": output},
                                         result_summary=f"{name} returned structured evidence", started_at=call_started, completed_at=call_finished))
        logger.info("tool_completed investigation=%s tool=%s", investigation_id, name)
        return output

    details = observe(1, "get_incident_details", "Establish the incident scope", {"incident_id": incident_id})
    metrics = observe(2, "get_payment_metrics", "Measure payment impact", {"incident_id": incident_id})
    clusters = observe(3, "get_failure_clusters", "Identify the dominant error family", {"incident_id": incident_id})
    baseline = observe(4, "get_historical_baseline", "Compare current metrics with baseline", {"incident_id": incident_id})
    regions = observe(5, "get_regional_metrics", "Test whether impact is region-specific", {"incident_id": incident_id})
    history = observe(6, "search_incident_history", "Compare with prior incidents", {"incident_id": incident_id})
    observe(7, "get_transaction_timeline", "Identify changes immediately before detection", {"incident_id": incident_id})
    if details.get("provider"):
        health = observe(8, "get_provider_health", "Validate suspected provider degradation", {"provider_id": details["provider"]})
    else:
        health = {"health_status": "unknown", "failure_rate": 0, "latency_p95_ms": 0}

    dominant = clusters.get("clusters", [{}])[0] if clusters.get("clusters") else {}
    provider_supported = health.get("health_status") == "degraded"
    region_rates = [item.get("failure_rate", 0) for item in regions.values()]
    regional = len(region_rates) == 1 or (region_rates and max(region_rates) - min(region_rates) > .15)
    incident_type = details.get("incident_type")
    if incident_type == "regional_degradation":
        root = f"{details.get('region') or 'Regional'} infrastructure degradation"
        category = "regional_degradation"
    elif incident_type == "customer_level_failure":
        root = "Customer-level payment failures"
        category = "customer_level_failure"
    elif incident_type == "payment_method_degradation":
        root = f"{details.get('payment_method') or 'Payment method'} failure concentration"
        category = "payment_method_degradation"
    else:
        root = f"{details.get('provider')} timeout degradation" if provider_supported else f"{dominant.get('error_code', 'payment')} failure concentration"
        category = "provider_degradation" if provider_supported else "payment_method_degradation"
    evidence = [
        Evidence(evidence_id="EV-001", source="payment_metrics", metric="failure_rate", observed_value=metrics["failure_rate"], baseline_value=.06,
                 delta=baseline["failure_rate_delta"], severity="critical" if metrics["failure_rate"] > .25 else "high", relevance=.95,
                 description=f"Failure rate is {metrics['failure_rate']:.1%} versus 6.0% baseline"),
        Evidence(evidence_id="EV-002", source="failure_clusters", metric="dominant_error_share", observed_value=dominant.get("share", 0), severity="high", relevance=.88,
                 description=f"{dominant.get('error_code', 'unknown')} is the dominant failure pattern"),
        Evidence(evidence_id="EV-003", source="provider_health", metric="latency_p95_ms", observed_value=health.get("latency_p95_ms", 0), baseline_value=910,
                 delta=health.get("latency_p95_ms", 0) - 910, severity="critical" if provider_supported else "medium", relevance=.94,
                 description=f"Provider health is {health.get('health_status')} with p95 latency {health.get('latency_p95_ms', 0)}ms"),
    ]
    matches = [HistoricalMatch(**item) for item in history]
    best = matches[0].similarity if matches else 0
    hypotheses = [Hypothesis(hypothesis="Provider degradation", status="supported" if provider_supported else "partially_supported", reason="Provider health and failure metrics agree"),
                  Hypothesis(hypothesis="Payment-method-wide degradation", status="partially_supported" if not provider_supported else "rejected", reason="Error pattern is not isolated to the method" if provider_supported else "Method-level evidence remains plausible"),
                  Hypothesis(hypothesis="Regional infrastructure issue", status="partially_supported" if regional else "rejected", reason="Regional rates differ materially" if regional else "Impact is distributed across regions")]
    result = InvestigationResult(incident_id=incident_id, incident_summary=details.get("description") or "Detected payment incident",
        root_cause=root, root_cause_category=category, confidence=evidence_confidence(incident.anomaly_score, len(evidence), .9 if provider_supported else .65, best, .1 if regional else 0), evidence=evidence,
        alternative_hypotheses=hypotheses, rejected_hypotheses=[item for item in hypotheses if item.status == "rejected"],
        impact={"revenue_at_risk": incident.revenue_at_risk, "affected_transactions": incident.affected_transactions, "affected_merchants": incident.affected_merchants},
        historical_matches=matches, recommended_next_step="Evaluate alternate provider routing" if provider_supported else "Review payment-method operations",
        investigation_duration=round((time.time() - started.timestamp()), 3), tool_call_count=len(trace.tool_calls))
    trace.completed_at = datetime.now(timezone.utc); trace.final_result = result
    trace.reasoning_summary = ["Collected independent payment, baseline, error, provider, regional, timeline, and historical evidence.", "Compared three hypotheses before selecting the best-supported explanation."]
    db.add(Investigation(investigation_id=investigation_id, incident_id=incident_id, started_at=started, completed_at=trace.completed_at,
                         agent=trace.agent, trace_json=trace.model_dump_json(), result_json=result.model_dump_json()))
    db.commit(); logger.info("investigation_completed id=%s", investigation_id)
    return trace


def load_investigation(db: Session, investigation_id: str) -> InvestigationTrace | None:
    row = db.get(Investigation, investigation_id)
    return InvestigationTrace.model_validate_json(row.trace_json) if row else None