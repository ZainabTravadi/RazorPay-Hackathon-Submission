from __future__ import annotations

import argparse
from typing import Any

import numpy as np
import pandas as pd

PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "Provider A": {
        "baseline_latency_ms": 210,
        "baseline_success_rate": 0.96,
        "payment_methods": ["UPI", "card", "netbanking", "wallet"],
    },
    "Provider B": {
        "baseline_latency_ms": 320,
        "baseline_success_rate": 0.93,
        "payment_methods": ["card", "UPI", "wallet"],
    },
    "Provider C": {
        "baseline_latency_ms": 280,
        "baseline_success_rate": 0.95,
        "payment_methods": ["netbanking", "wallet", "UPI"],
    },
}

PAYMENT_METHODS = ["UPI", "card", "netbanking", "wallet"]
REGIONS = ["Mumbai", "Bengaluru", "Delhi", "Hyderabad", "Chennai", "Ahmedabad", "Pune", "Kolkata"]
DEVICES = ["android", "ios", "web"]
MERCHANT_CATEGORIES = ["ecommerce", "SaaS", "travel", "food", "education", "retail"]

MERCHANTS = [
    ("M1001", "Aster Retail", "retail", "Mumbai"),
    ("M1002", "Bluebird Labs", "SaaS", "Bengaluru"),
    ("M1003", "Mitra Travel", "travel", "Delhi"),
    ("M1004", "SpiceBite", "food", "Hyderabad"),
    ("M1005", "LearnNest", "education", "Chennai"),
    ("M1006", "CityCart", "ecommerce", "Ahmedabad"),
    ("M1007", "PulseNet", "SaaS", "Pune"),
    ("M1008", "Kolkata Market", "retail", "Kolkata"),
    ("M1009", "MangoBox", "food", "Mumbai"),
    ("M1010", "Vistara Deals", "travel", "Bengaluru"),
    ("M1011", "SkillCampus", "education", "Delhi"),
    ("M1012", "UrbanStore", "ecommerce", "Hyderabad"),
    ("M1013", "NorthLoop", "retail", "Ahmedabad"),
    ("M1014", "CloudPilot", "SaaS", "Chennai"),
    ("M1015", "QuickMiles", "travel", "Pune"),
    ("M1016", "CurryCircle", "food", "Kolkata"),
    ("M1017", "VedaAcademy", "education", "Mumbai"),
    ("M1018", "PocketCart", "ecommerce", "Bengaluru"),
    ("M1019", "PrimeRetail", "retail", "Delhi"),
    ("M1020", "JetLane", "travel", "Ahmedabad"),
    ("M1021", "Zealio", "SaaS", "Kolkata"),
    ("M1022", "FreshBite", "food", "Pune"),
    ("M1023", "EduBridge", "education", "Hyderabad"),
    ("M1024", "OneCart", "ecommerce", "Chennai"),
]

ERROR_CODE_MAP = {
    "timeout": ["gateway_timeout", "provider_timeout", "upi_timeout", "issuer_timeout"],
    "decline": ["insufficient_funds", "invalid_card", "authentication_failure", "card_declined"],
    "network": ["network_error", "provider_outage", "temporary_unavailable"],
}


def _weighted_provider_choice(rng: np.random.Generator) -> str:
    provider_weights = np.array([0.46, 0.34, 0.20], dtype=float)
    return str(rng.choice(list(PROVIDER_CONFIG.keys()), p=provider_weights))


def _weighted_method_choice(rng: np.random.Generator, provider: str) -> str:
    method_map = {
        "Provider A": ["UPI", "UPI", "card", "wallet", "netbanking"],
        "Provider B": ["card", "card", "UPI", "wallet", "netbanking"],
        "Provider C": ["netbanking", "wallet", "UPI", "card", "wallet"],
    }
    return str(rng.choice(method_map[provider]))


def _generate_merchant_weights() -> list[tuple[str, float]]:
    merchants = []
    for idx, _ in enumerate(MERCHANTS):
        weight = 0.8 + (idx % 7) * 0.2
        merchants.append((MERCHANTS[idx][0], weight))
    return merchants


def generate_payments(events: int = 100000, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic payment data with deterministic distributions."""
    rng = np.random.default_rng(seed)
    merchant_weights = _generate_merchant_weights()
    merchant_ids = [item[0] for item in merchant_weights]
    merchant_prob = np.array([item[1] for item in merchant_weights], dtype=float)
    merchant_prob = merchant_prob / merchant_prob.sum()

    payment_rows: list[dict[str, Any]] = []
    start_time = pd.Timestamp("2025-01-01T00:00:00Z")
    end_time = start_time + pd.Timedelta(days=40)
    total_seconds = int((end_time - start_time).total_seconds())

    for idx in range(int(events)):
        provider = _weighted_provider_choice(rng)
        payment_method = _weighted_method_choice(rng, provider)
        region = str(rng.choice(REGIONS, p=np.array([0.18, 0.16, 0.15, 0.12, 0.10, 0.09, 0.10, 0.10], dtype=float)))
        device = str(rng.choice(DEVICES, p=[0.46, 0.35, 0.19]))
        merchant_id = str(rng.choice(merchant_ids, p=merchant_prob))
        amount = float(np.clip(rng.lognormal(mean=4.2, sigma=1.15), 50.0, 30000.0))
        timestamp = start_time + pd.to_timedelta(rng.integers(0, total_seconds), unit="s")

        provider_config = PROVIDER_CONFIG[provider]
        success_base = provider_config["baseline_success_rate"]
        method_bonus = {"UPI": 0.98, "card": 1.02, "netbanking": 0.96, "wallet": 1.0}[payment_method]
        region_bonus = {"Mumbai": 1.03, "Bengaluru": 1.02, "Delhi": 1.01, "Hyderabad": 1.0, "Chennai": 0.99, "Ahmedabad": 0.97, "Pune": 1.0, "Kolkata": 0.98}[region]
        success_probability = float(np.clip(success_base * method_bonus * region_bonus, 0.70, 0.995))
        status_roll = rng.random()

        if status_roll < success_probability:
            if rng.random() < 0.10:
                status = "authorized"
            elif rng.random() < 0.08:
                status = "pending"
            else:
                status = "captured"
            if rng.random() < 0.06:
                status = "refunded"
            error_code = None
            error_source = None
            error_step = None
            error_reason = None
        else:
            status = "failed"
            error_code = str(rng.choice(["gateway_timeout", "insufficient_funds", "invalid_card", "authentication_failure", "provider_outage", "upi_timeout", "network_error"]))
            error_source = str(rng.choice(["gateway", "issuer", "network", "customer"]))
            error_step = str(rng.choice(["authorization", "capture", "validation", "webhook"]))
            error_reason = str(rng.choice(["timeout", "insufficient_funds", "invalid_card", "auth_failed", "transient_network", "merchant_misconfig"]))

        latency_ms = float(
            np.clip(
                rng.normal(loc=provider_config["baseline_latency_ms"], scale=90) + (0 if payment_method == "UPI" else 25),
                80,
                8000,
            )
        )

        if status == "failed":
            latency_ms = float(np.clip(latency_ms * (1.5 + rng.random() * 1.3), 180, 9000))

        row = {
            "payment_id": f"PAY-{idx:08d}",
            "merchant_id": merchant_id,
            "amount": round(amount, 2),
            "currency": "INR",
            "timestamp": timestamp,
            "payment_method": payment_method,
            "provider": provider,
            "region": region,
            "device": device,
            "status": status,
            "error_code": error_code,
            "error_source": error_source,
            "error_step": error_step,
            "error_reason": error_reason,
            "latency_ms": round(latency_ms, 2),
        }
        payment_rows.append(row)

    df = pd.DataFrame(payment_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic payment traffic for FluxPay.")
    parser.add_argument("--events", type=int, default=100000, help="Number of payment events to generate.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed.")
    args = parser.parse_args()

    data = generate_payments(events=args.events, seed=args.seed)
    print(data.head(5).to_json(orient="records", date_format="iso"))
