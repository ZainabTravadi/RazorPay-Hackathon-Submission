from __future__ import annotations

import argparse
import os
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from data.generator.generate import MERCHANTS, PROVIDER_CONFIG, generate_payments
from database.base import Base
from database.models import HistoricalIncident, Incident, Merchant, Payment, Provider
from database.session import SessionLocal, engine


HISTORICAL_INCIDENTS: list[dict[str, Any]] = [
    {
        "incident_id": "HIST-001",
        "incident_type": "provider_outage",
        "fingerprint": "UPI|PROVIDER B|AHMEDABAD|OUTAGE|CRITICAL",
        "root_cause": "Regional provider degradation triggered timeout cascades.",
        "resolution": "Re-routed packets to backup provider and increased retries.",
        "recovery_rate": 0.7,
        "revenue_impact": 420000.0,
        "timestamp": "2025-01-05T14:00:00Z",
    },
    {
        "incident_id": "HIST-002",
        "incident_type": "provider_latency",
        "fingerprint": "CARD|PROVIDER B|MUMBAI|TIMEOUT|HIGH",
        "root_cause": "Latency spike from internal gateway saturation.",
        "resolution": "Scaled queue throughput and throttled retries.",
        "recovery_rate": 0.75,
        "revenue_impact": 260000.0,
        "timestamp": "2025-01-08T14:15:00Z",
    },
    {
        "incident_id": "HIST-003",
        "incident_type": "upi_degradation",
        "fingerprint": "UPI|PROVIDER A|DELHI|TIMEOUT|HIGH",
        "root_cause": "UPI gateway degraded across a metro cluster.",
        "resolution": "Shifted processing to fallback path and raised provider dedupe thresholds.",
        "recovery_rate": 0.68,
        "revenue_impact": 210000.0,
        "timestamp": "2025-01-11T08:30:00Z",
    },
    {
        "incident_id": "HIST-004",
        "incident_type": "regional_degradation",
        "fingerprint": "CARD|PROVIDER C|AHMEDABAD|TIMEOUT|MEDIUM",
        "root_cause": "Regional network congestion degraded card auth completion.",
        "resolution": "Fallbacked to alternate route and rebalanced PQ.",
        "recovery_rate": 0.6,
        "revenue_impact": 145000.0,
        "timestamp": "2025-01-12T19:00:00Z",
    },
    {
        "incident_id": "HIST-005",
        "incident_type": "merchant_misconfiguration",
        "fingerprint": "UPI|PROVIDER A|BENGALURU|UNKNOWN|MEDIUM",
        "root_cause": "One merchant misconfigured callback endpoint for payment confirmation.",
        "resolution": "Reconfigured merchant webhook URL and revalidated signatures.",
        "recovery_rate": 0.9,
        "revenue_impact": 35000.0,
        "timestamp": "2025-01-15T09:45:00Z",
    },
    {
        "incident_id": "HIST-006",
        "incident_type": "customer_level_failure",
        "fingerprint": "CARD|PROVIDER C|CHENNAI|CUSTOMER|LOW",
        "root_cause": "Issuer declines clustered around customer payment instrument refresh events.",
        "resolution": "Customer retry guidance and instrument validation.",
        "recovery_rate": 0.15,
        "revenue_impact": 62000.0,
        "timestamp": "2025-01-17T13:20:00Z",
    },
    {
        "incident_id": "HIST-007",
        "incident_type": "webhook_failure",
        "fingerprint": "CARD|PROVIDER A|MUMBAI|OUTAGE|LOW",
        "root_cause": "Webhook retry queue dropped delivery events after traffic burst.",
        "resolution": "Replayed queued webhook payloads and increased TTL.",
        "recovery_rate": 0.85,
        "revenue_impact": 49000.0,
        "timestamp": "2025-01-18T05:00:00Z",
    },
    {
        "incident_id": "HIST-008",
        "incident_type": "late_authorization",
        "fingerprint": "UPI|PROVIDER A|PUNE|UNKNOWN|MEDIUM",
        "root_cause": "Authorization callback arrived late after a downstream timeout.",
        "resolution": "Introduced manual reconciliation and extended timeout window.",
        "recovery_rate": 0.8,
        "revenue_impact": 76000.0,
        "timestamp": "2025-01-20T12:00:00Z",
    },
    {
        "incident_id": "HIST-009",
        "incident_type": "normal_traffic_spike",
        "fingerprint": "CARD|PROVIDER A|MUMBAI|NORMAL|LOW",
        "root_cause": "Seasonal traffic increase without underlying degradation.",
        "resolution": "Autoscaling and no incident actions required.",
        "recovery_rate": 0.98,
        "revenue_impact": 15000.0,
        "timestamp": "2025-01-23T21:00:00Z",
    },
    {
        "incident_id": "HIST-010",
        "incident_type": "mixed_incident",
        "fingerprint": "UPI|PROVIDER B|AHMEDABAD|TIMEOUT|HIGH",
        "root_cause": "Provider B latency spike overlapped with UPI degradation in Ahmedabad.",
        "resolution": "Rebalanced traffic to Provider C and isolated Ahmedabad cluster.",
        "recovery_rate": 0.65,
        "revenue_impact": 510000.0,
        "timestamp": "2025-01-26T17:30:00Z",
    },
    {
        "incident_id": "HIST-011",
        "incident_type": "provider_outage",
        "fingerprint": "NETBANKING|PROVIDER C|DELHI|OUTAGE|CRITICAL",
        "root_cause": "Provider C edge outage affecting a subset of netbanking retries.",
        "resolution": "Failed over to Provider A and cleared stale queues.",
        "recovery_rate": 0.72,
        "revenue_impact": 382000.0,
        "timestamp": "2025-01-27T11:35:00Z",
    },
    {
        "incident_id": "HIST-012",
        "incident_type": "provider_latency",
        "fingerprint": "WALLET|PROVIDER A|BENGALURU|TIMEOUT|MEDIUM",
        "root_cause": "Wallet authorization latency increased due to upstream dependency.",
        "resolution": "Backoff tuning and queue drain.",
        "recovery_rate": 0.8,
        "revenue_impact": 110000.0,
        "timestamp": "2025-01-29T03:20:00Z",
    },
    {
        "incident_id": "HIST-013",
        "incident_type": "regional_degradation",
        "fingerprint": "UPI|PROVIDER B|KOLKATA|TIMEOUT|MEDIUM",
        "root_cause": "Kolkata cluster saw elevated UPI retry storms.",
        "resolution": "Rate limit increased and retries short-circuited.",
        "recovery_rate": 0.7,
        "revenue_impact": 190000.0,
        "timestamp": "2025-02-02T10:10:00Z",
    },
    {
        "incident_id": "HIST-014",
        "incident_type": "customer_level_failure",
        "fingerprint": "CARD|PROVIDER B|HYDERABAD|CUSTOMER|LOW",
        "root_cause": "Customer bank-side limit triggers caused clustered declines.",
        "resolution": "Customer outreach and retry guidance.",
        "recovery_rate": 0.12,
        "revenue_impact": 44000.0,
        "timestamp": "2025-02-05T16:45:00Z",
    },
    {
        "incident_id": "HIST-015",
        "incident_type": "merchant_misconfiguration",
        "fingerprint": "CARD|PROVIDER C|PUNE|UNKNOWN|MEDIUM",
        "root_cause": "Merchant callback certificate rotation caused missed confirmations.",
        "resolution": "Certificate replacement and replay queue fix.",
        "recovery_rate": 0.86,
        "revenue_impact": 54000.0,
        "timestamp": "2025-02-08T20:15:00Z",
    },
    {
        "incident_id": "HIST-016",
        "incident_type": "webhook_failure",
        "fingerprint": "WALLET|PROVIDER C|MUMBAI|OUTAGE|LOW",
        "root_cause": "Webhook queue saturation delayed settlement callbacks.",
        "resolution": "Queue drains and retry back-pressure fix.",
        "recovery_rate": 0.88,
        "revenue_impact": 36000.0,
        "timestamp": "2025-02-10T12:00:00Z",
    },
    {
        "incident_id": "HIST-017",
        "incident_type": "upi_degradation",
        "fingerprint": "UPI|PROVIDER C|CHENNAI|TIMEOUT|MEDIUM",
        "root_cause": "UPI app routing degradation around a telecom event.",
        "resolution": "Shared load balancing and failover to alternate route.",
        "recovery_rate": 0.72,
        "revenue_impact": 165000.0,
        "timestamp": "2025-02-13T14:05:00Z",
    },
    {
        "incident_id": "HIST-018",
        "incident_type": "provider_outage",
        "fingerprint": "CARD|PROVIDER B|AHMEDABAD|OUTAGE|HIGH",
        "root_cause": "Partial auth failure at Provider B due to queue outage.",
        "resolution": "Cleared queue and shifted traffic to provider A.",
        "recovery_rate": 0.66,
        "revenue_impact": 280000.0,
        "timestamp": "2025-02-16T09:20:00Z",
    },
    {
        "incident_id": "HIST-019",
        "incident_type": "normal_traffic_spike",
        "fingerprint": "WALLET|PROVIDER A|DELHI|NORMAL|LOW",
        "root_cause": "High-volume month-end traffic; no payment issue observed.",
        "resolution": "No remediation required; normalized without alerts.",
        "recovery_rate": 0.99,
        "revenue_impact": 22000.0,
        "timestamp": "2025-02-18T18:40:00Z",
    },
    {
        "incident_id": "HIST-020",
        "incident_type": "mixed_incident",
        "fingerprint": "CARD|PROVIDER B|DELHI|TIMEOUT|HIGH",
        "root_cause": "Card payment latency and regional UPI issue overlap.",
        "resolution": "Traffic shifted to fallback with tightened rate limits.",
        "recovery_rate": 0.62,
        "revenue_impact": 430000.0,
        "timestamp": "2025-02-20T19:40:00Z",
    },
    {
        "incident_id": "HIST-021",
        "incident_type": "provider_latency",
        "fingerprint": "NETBANKING|PROVIDER A|MUMBAI|TIMEOUT|MEDIUM",
        "root_cause": "Authentication service slowdown created long tails.",
        "resolution": "Async queue and timeout tuning.",
        "recovery_rate": 0.77,
        "revenue_impact": 98000.0,
        "timestamp": "2025-02-22T05:00:00Z",
    },
    {
        "incident_id": "HIST-022",
        "incident_type": "regional_degradation",
        "fingerprint": "CARD|PROVIDER C|AHMEDABAD|TIMEOUT|MEDIUM",
        "root_cause": "Regional auth cluster degraded from packet loss.",
        "resolution": "Node balancing and route re-selection.",
        "recovery_rate": 0.68,
        "revenue_impact": 200000.0,
        "timestamp": "2025-02-26T15:40:00Z",
    },
    {
        "incident_id": "HIST-023",
        "incident_type": "merchant_misconfiguration",
        "fingerprint": "UPI|PROVIDER A|MUMBAI|UNKNOWN|LOW",
        "root_cause": "Merchant app key mismatch impacted only one merchant cluster.",
        "resolution": "Key rotation and validation complete.",
        "recovery_rate": 0.92,
        "revenue_impact": 28000.0,
        "timestamp": "2025-03-01T07:10:00Z",
    },
    {
        "incident_id": "HIST-024",
        "incident_type": "customer_level_failure",
        "fingerprint": "UPI|PROVIDER B|HYDERABAD|CUSTOMER|LOW",
        "root_cause": "Low-balance UPI failures distributed across customers.",
        "resolution": "Customer retry guidance and wallet balance checks.",
        "recovery_rate": 0.18,
        "revenue_impact": 55000.0,
        "timestamp": "2025-03-04T11:50:00Z",
    },
    {
        "incident_id": "HIST-025",
        "incident_type": "late_authorization",
        "fingerprint": "CARD|PROVIDER B|KOLKATA|UNKNOWN|MEDIUM",
        "root_cause": "Authorization confirmation arrived after timeout window.",
        "resolution": "Extended reconciliation and automated status correction.",
        "recovery_rate": 0.82,
        "revenue_impact": 71000.0,
        "timestamp": "2025-03-07T08:30:00Z",
    },
    {
        "incident_id": "HIST-026",
        "incident_type": "webhook_failure",
        "fingerprint": "NETBANKING|PROVIDER A|CHENNAI|OUTAGE|LOW",
        "root_cause": "Delayed webhook delivery after queue delay.",
        "resolution": "Replay of undelivered events and queue scaling.",
        "recovery_rate": 0.9,
        "revenue_impact": 41000.0,
        "timestamp": "2025-03-11T16:20:00Z",
    },
    {
        "incident_id": "HIST-027",
        "incident_type": "provider_latency",
        "fingerprint": "CARD|PROVIDER C|BENGALURU|TIMEOUT|HIGH",
        "root_cause": "Card issuer latency increased during region-wide keystore sync.",
        "resolution": "Recovery from keystore drift and queue reset.",
        "recovery_rate": 0.79,
        "revenue_impact": 245000.0,
        "timestamp": "2025-03-14T12:15:00Z",
    },
    {
        "incident_id": "HIST-028",
        "incident_type": "upi_degradation",
        "fingerprint": "UPI|PROVIDER A|AHMEDABAD|TIMEOUT|HIGH",
        "root_cause": "UPI traffic in Ahmedabad exceeded routing capacity.",
        "resolution": "Route balancing and surge guard enabled.",
        "recovery_rate": 0.73,
        "revenue_impact": 212000.0,
        "timestamp": "2025-03-18T09:25:00Z",
    },
    {
        "incident_id": "HIST-029",
        "incident_type": "provider_outage",
        "fingerprint": "WALLET|PROVIDER A|DELHI|OUTAGE|MEDIUM",
        "root_cause": "Provider A wallet processing outage broke a small percent of traffic.",
        "resolution": "Fallback to alternate routing and queue flush.",
        "recovery_rate": 0.74,
        "revenue_impact": 115000.0,
        "timestamp": "2025-03-22T18:00:00Z",
    },
    {
        "incident_id": "HIST-030",
        "incident_type": "mixed_incident",
        "fingerprint": "UPI|PROVIDER B|AHMEDABAD|TIMEOUT|CRITICAL",
        "root_cause": "Mixed Ahmedabad regional issue and Provider B latency spike triggered maximum impact.",
        "resolution": "Provider failover, queue isolation, and regional route control.",
        "recovery_rate": 0.63,
        "revenue_impact": 620000.0,
        "timestamp": "2025-03-25T20:00:00Z",
    },
]


def _reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_merchants(db: Session) -> None:
    for merchant_id, merchant_name, category, region in MERCHANTS:
        merchant = db.get(Merchant, merchant_id)
        if merchant is None:
            db.add(Merchant(
                merchant_id=merchant_id,
                merchant_name=merchant_name,
                category=category,
                region=region,
            ))
    db.commit()


def _seed_providers(db: Session) -> None:
    for provider_name, config in PROVIDER_CONFIG.items():
        provider_id = provider_name.lower().replace(" ", "_")
        provider = db.get(Provider, provider_id)
        if provider is None:
            db.add(Provider(
                provider_id=provider_id,
                provider_name=provider_name,
                payment_methods=",".join(config["payment_methods"]),
                baseline_latency_ms=config["baseline_latency_ms"],
                baseline_success_rate=config["baseline_success_rate"],
                health_status="healthy",
            ))
    db.commit()


def _seed_payments(db: Session, events: int, seed: int) -> None:
    existing_count = db.query(Payment).count()
    if existing_count >= events:
        return
    df = generate_payments(events=events, seed=seed)
    for row in df.to_dict(orient="records"):
        db.add(Payment(
            payment_id=row["payment_id"],
            merchant_id=row["merchant_id"],
            amount=row["amount"],
            currency=row["currency"],
            timestamp=row["timestamp"],
            payment_method=row["payment_method"],
            provider=row["provider"],
            region=row["region"],
            device=row["device"],
            status=row["status"],
            error_code=row["error_code"],
            error_source=row["error_source"],
            error_step=row["error_step"],
            error_reason=row["error_reason"],
            latency_ms=row["latency_ms"],
        ))
    db.commit()


def _seed_historical_incidents(db: Session) -> None:
    for incident in HISTORICAL_INCIDENTS:
        if db.get(HistoricalIncident, incident["incident_id"]) is None:
            db.add(HistoricalIncident(
                incident_id=incident["incident_id"],
                incident_type=incident["incident_type"],
                fingerprint=incident["fingerprint"],
                root_cause=incident["root_cause"],
                resolution=incident["resolution"],
                recovery_rate=incident["recovery_rate"],
                revenue_impact=incident["revenue_impact"],
                timestamp=pd.Timestamp(incident["timestamp"]).to_pydatetime(),
            ))
    db.commit()


def seed_database(*, events: int = 100000, seed: int = 42, reset: bool = False) -> dict[str, Any]:
    db = SessionLocal()
    try:
        if reset:
            _reset_database()
        Base.metadata.create_all(bind=engine)
        _seed_merchants(db)
        _seed_providers(db)
        _seed_payments(db, events=events, seed=seed)
        _seed_historical_incidents(db)
        payment_count = db.query(Payment).count()
        historical_incident_count = db.query(HistoricalIncident).count()
        return {
            "status": "ok",
            "payments": payment_count,
            "historical_incidents": historical_incident_count,
            "reset": reset,
            "seed": seed,
            "synthetic": True,
        }
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic FluxPay data into the configured database.")
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    result = seed_database(events=args.events, seed=args.seed, reset=args.reset)
    print(result)
