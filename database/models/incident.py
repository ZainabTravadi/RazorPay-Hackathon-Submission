from __future__ import annotations

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="detected")
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    affected_transactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_merchants: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_at_risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    primary_provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    primary_payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    primary_region: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_incident_severity_valid"),
        CheckConstraint("anomaly_score >= 0", name="ck_incident_anomaly_score_nonnegative"),
        CheckConstraint("affected_transactions >= 0", name="ck_incident_affected_transactions_nonnegative"),
    )
