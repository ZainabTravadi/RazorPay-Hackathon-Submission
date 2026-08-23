from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Provider(Base):
    __tablename__ = "providers"

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    payment_methods: Mapped[str] = mapped_column(String(255), nullable=False)
    baseline_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_success_rate: Mapped[float] = mapped_column(Float, nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="healthy")
