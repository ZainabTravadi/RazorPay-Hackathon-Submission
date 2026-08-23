from __future__ import annotations

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class HistoricalIncident(Base):
    __tablename__ = "historical_incidents"

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_rate: Mapped[float] = mapped_column(Float, nullable=False)
    revenue_impact: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
