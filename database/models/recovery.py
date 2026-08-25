from __future__ import annotations

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class RecoveryExecutionRecord(Base):
    __tablename__ = "recovery_executions"

    recovery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)


class RecoveryAttemptRecord(Base):
    __tablename__ = "recovery_attempts"

    attempt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recovery_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_executions.recovery_id"), index=True, nullable=False)
    incident_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payment_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(nullable=False, default=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recovered_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("recovery_id", "payment_id", "attempt_number", name="uq_recovery_payment_attempt"),
    )


class RecoveryEventRecord(Base):
    __tablename__ = "recovery_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recovery_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_executions.recovery_id"), index=True, nullable=False)
    incident_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)