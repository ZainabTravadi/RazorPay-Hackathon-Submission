from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from apps.api.schemas.investigation import Evidence, HistoricalMatch, Hypothesis


ReplayPhase = Literal["before_incident", "detection", "investigation", "root_cause", "recovery", "resolution"]
ReplaySource = Literal["incident", "historical"]


class ReplayIncidentSummary(BaseModel):
    incident_id: str
    source_kind: ReplaySource
    incident_type: str | None = None
    severity: str | None = None
    status: str | None = None
    anomaly_score: float | None = None
    started_at: datetime
    detected_at: datetime | None = None
    ended_at: datetime | None = None
    primary_provider: str | None = None
    primary_payment_method: str | None = None
    primary_region: str | None = None
    description: str | None = None
    fingerprint: str | None = None


class ReplaySnapshot(BaseModel):
    phase: ReplayPhase
    signal_summary: str
    failure_rate: float | None = None
    success_rate: float | None = None
    provider_latency_p95_ms: float | None = None
    affected_transactions: int | None = None
    affected_merchants: int | None = None
    revenue_at_risk: float | None = None
    confidence: float | None = None
    evidence_count: int = 0
    root_cause: str | None = None
    recommendation: str | None = None
    approval_status: str | None = None
    execution_status: str | None = None
    investigation_id: str | None = None
    recovery_id: str | None = None
    incident_status: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    impact: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    historical_matches: list[HistoricalMatch] = Field(default_factory=list)


class ReplayEvent(BaseModel):
    event_id: str
    index: int
    type: str
    timestamp: datetime
    title: str
    description: str
    phase: ReplayPhase
    severity: Literal["low", "medium", "high", "critical", "info"] = "info"
    incident_id: str
    investigation_id: str | None = None
    recovery_id: str | None = None
    snapshot: ReplaySnapshot
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayTimeline(BaseModel):
    incident: ReplayIncidentSummary
    start_at: datetime
    end_at: datetime
    duration_seconds: float
    event_count: int
    replayable: bool = True
    deterministic: bool = True
    has_investigation: bool = False
    has_recovery: bool = False
    current_phase: ReplayPhase
    events: list[ReplayEvent] = Field(default_factory=list)
