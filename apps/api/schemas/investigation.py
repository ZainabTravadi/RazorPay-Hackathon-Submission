from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str
    source: str
    metric: str
    observed_value: Any
    baseline_value: Any | None = None
    delta: float | None = None
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    timestamp: datetime | None = None
    relevance: float = Field(ge=0, le=1)
    description: str


class Hypothesis(BaseModel):
    hypothesis: str
    status: Literal["supported", "partially_supported", "rejected"]
    reason: str


class HistoricalMatch(BaseModel):
    incident_id: str
    similarity: float = Field(ge=0, le=1)
    root_cause: str
    resolution: str
    recovery_rate: float


class InvestigationResult(BaseModel):
    incident_id: str
    incident_summary: str
    root_cause: str
    root_cause_category: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence]
    alternative_hypotheses: list[Hypothesis]
    rejected_hypotheses: list[Hypothesis]
    impact: dict[str, Any]
    historical_matches: list[HistoricalMatch]
    recommended_next_step: str
    investigation_duration: float
    tool_call_count: int


class ToolCall(BaseModel):
    step: int
    tool: str
    purpose: str
    inputs: dict[str, Any]
    output: dict[str, Any]
    result_summary: str
    started_at: datetime
    completed_at: datetime


class InvestigationTrace(BaseModel):
    investigation_id: str
    incident_id: str
    started_at: datetime
    completed_at: datetime | None = None
    agent: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning_summary: list[str] = Field(default_factory=list)
    final_result: InvestigationResult | None = None