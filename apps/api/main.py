from __future__ import annotations

from typing import Any
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routes import dashboard, historical_incidents, incidents, metrics, payments, providers, simulator, investigations, recovery, replay
from database.init_db import init_db

app = FastAPI(title="FluxPay", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(historical_incidents.router)
app.include_router(incidents.router)
app.include_router(metrics.router)
app.include_router(payments.router)
app.include_router(providers.router)
app.include_router(simulator.router)
app.include_router(investigations.router)
app.include_router(recovery.router)
app.include_router(replay.router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "fluxpay-api", "synthetic": True}
