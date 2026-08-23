from __future__ import annotations

import pandas as pd

from data.generator.generate import generate_payments
from ml.anomaly.detector import detect_anomalies
from ml.fingerprinting.fingerprint import build_fingerprint, fingerprint_similarity
from ml.metrics.revenue import compute_revenue_at_risk


def test_payment_generation_is_deterministic() -> None:
    data_a = generate_payments(events=2000, seed=42)
    data_b = generate_payments(events=2000, seed=42)
    assert data_a.equals(data_b)
    assert len(data_a) == 2000


def test_payment_generation_has_expected_columns() -> None:
    df = generate_payments(events=1500, seed=7)
    required = {
        "payment_id",
        "merchant_id",
        "amount",
        "currency",
        "timestamp",
        "payment_method",
        "provider",
        "region",
        "device",
        "status",
        "error_code",
        "error_source",
        "error_step",
        "error_reason",
        "latency_ms",
    }
    assert required.issubset(df.columns)


def test_provider_outage_is_detected() -> None:
    base = generate_payments(events=5000, seed=11)
    outage = base.copy()
    outage.loc[outage["provider"] == "Provider B", "status"] = "failed"
    outage.loc[outage["provider"] == "Provider B", "error_code"] = "provider_outage"
    outage.loc[outage["provider"] == "Provider B", "latency_ms"] = 9000
    anomalies = detect_anomalies(outage)
    assert any(a["entity"] == "Provider B" and a["metric"] == "failure_rate" for a in anomalies)


def test_upi_degradation_is_detected() -> None:
    base = generate_payments(events=5000, seed=11)
    degraded = base.copy()
    degraded.loc[degraded["payment_method"] == "UPI", "status"] = "failed"
    degraded.loc[degraded["payment_method"] == "UPI", "error_code"] = "upi_timeout"
    anomalies = detect_anomalies(degraded)
    assert any(a["entity"] == "UPI" and a["metric"] == "failure_rate" for a in anomalies)


def test_normal_traffic_spike_is_not_an_incident() -> None:
    base = generate_payments(events=5000, seed=17)
    spike = base.copy()
    spike["timestamp"] = pd.to_datetime(spike["timestamp"]) + pd.Timedelta(hours=4)
    anomalies = detect_anomalies(spike)
    assert not any(a["metric"] == "failure_rate" and a["is_anomaly"] and a["entity"] in {"Provider A", "Provider B"} for a in anomalies)


def test_fingerprint_similarity_works() -> None:
    fp1 = build_fingerprint("UPI", "Provider B", "Ahmedabad", "TIMEOUT", "HIGH")
    fp2 = build_fingerprint("UPI", "Provider B", "Ahmedabad", "TIMEOUT", "HIGH")
    fp3 = build_fingerprint("CARD", "Provider A", "Mumbai", "TIMEOUT", "MEDIUM")
    assert fp1 == fp2
    assert fingerprint_similarity(fp1, fp2) > 0.9
    assert fingerprint_similarity(fp1, fp3) < 0.8


def test_revenue_at_risk_is_calculated() -> None:
    rows = [
        {"amount": 500.0, "status": "failed", "error_code": "provider_timeout", "merchant_id": "m1"},
        {"amount": 200.0, "status": "failed", "error_code": "insufficient_funds", "merchant_id": "m2"},
        {"amount": 1200.0, "status": "failed", "error_code": "invalid_card", "merchant_id": "m3"},
    ]
    result = compute_revenue_at_risk(rows)
    assert result["gross_failed_amount"] == 1900.0
    assert result["estimated_recoverable_revenue"] > 0
    assert result["revenue_at_risk"] > 0
