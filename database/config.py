from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

POSTGRES_DEFAULT = "postgresql+psycopg2://fluxpay:fluxpay@localhost:5432/fluxpay"
SQLITE_FALLBACK = "sqlite:///./fluxpay.db"


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    return SQLITE_FALLBACK
