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


class RecoveryExecutionRequest(BaseModel):
    max_retries: int = Field(default=0, ge=0, le=10)
    fallback_strategy: str | None = "provider_failover"
    failure_rate_threshold: float = Field(default=1.0, ge=0, le=1)
    recovery_window_seconds: int = Field(default=86400, ge=0)
    primary_outcomes: list[Literal["success", "failure"]] | None = None
    fallback_outcomes: list[Literal["success", "failure"]] | None = None


class RecoveryExecution(BaseModel):
    recovery_id: str
    incident_id: str
    strategy: str
    status: Literal["pending", "approved", "running", "retrying", "escalated", "blocked", "completed", "failed", "cancelled"] = "pending"
    approval_status: Literal["pending", "approved", "rejected", "cancelled"]
    execution_status: Literal["not_started", "running", "retrying", "escalated", "completed", "blocked", "failed", "cancelled"]
    before_metrics: dict[str, Any]
    after_metrics: dict[str, Any] | None = None
    recovered_transactions: int = 0
    recovered_revenue: float = 0
    recovery_rate: float = 0
    simulated_latency_impact_ms: float = 0
    simulation: bool = True
    max_retries: int = 0
    fallback_strategy: str | None = "provider_failover"
    failure_rate_threshold: float = 1.0
    recovery_window_seconds: int = 86400
    stop_reason: str | None = None
    triggering_rule: str | None = None
    timestamp: datetime


class RecoveryAttempt(BaseModel):
    attempt_id: str
    recovery_id: str
    incident_id: str
    payment_id: str
    attempt_number: int
    strategy: str
    status: Literal["success", "failed"]
    success: bool
    amount: float
    recovered_amount: float = 0.0
    failure_reason: str | None = None
    timestamp: datetime


class RecoveryEvent(BaseModel):
    event_id: str
    recovery_id: str
    incident_id: str
    payment_id: str | None = None
    event_type: str
    reason: str | None = None
    metadata_json: dict[str, Any] | None = None
    timestamp: datetime