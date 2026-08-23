from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ImpactAnalysis(BaseModel):
    incident_id: str
    affected_transactions: int
    affected_merchants: int
    affected_payment_methods: list[str]
    affected_providers: list[str]
    failed_transactions: int
    affected_transaction_value: float
    revenue_at_risk: float
    estimated_recoverable_transactions: int
    estimated_recoverable_revenue: float
    incident_duration_minutes: float
    baseline_success_rate: float
    degraded_success_rate: float
    success_rate_delta: float


class RecoveryRecommendation(BaseModel):
    incident_id: str
    strategy: Literal["provider_failover", "bounded_retry", "alternative_method", "delayed_retry", "no_action"]
    reason: str
    expected_benefit: str
    estimated_recoverable_transactions: int
    estimated_recoverable_revenue: float
    confidence: float = Field(ge=0, le=1)
    assumptions: list[str]
    risks: list[str]


class PolicyDecision(BaseModel):
    allowed: bool
    requires_human_approval: bool
    risk_level: Literal["low", "medium", "high"]
    reasons: list[str]
    blocked_actions: list[str]


class RecoveryExecution(BaseModel):
    recovery_id: str
    incident_id: str
    strategy: str
    approval_status: Literal["pending", "approved", "rejected", "cancelled"]
    execution_status: Literal["not_started", "completed", "blocked", "failed"]
    before_metrics: dict[str, Any]
    after_metrics: dict[str, Any] | None = None
    recovered_transactions: int = 0
    recovered_revenue: float = 0
    recovery_rate: float = 0
    simulated_latency_impact_ms: float = 0
    simulation: bool = True
    timestamp: datetime