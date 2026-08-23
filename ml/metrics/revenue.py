from __future__ import annotations

from collections.abc import Iterable

RECOVERABILITY_PROBABILITIES = {
    "provider_timeout": 0.75,
    "provider_outage": 0.70,
    "insufficient_funds": 0.10,
    "invalid_card": 0.05,
    "authentication_failure": 0.25,
    "upi_timeout": 0.68,
    "gateway_timeout": 0.72,
    "network_error": 0.55,
    "unknown": 0.20,
}


def compute_revenue_at_risk(rows: Iterable[dict]) -> dict[str, float]:
    """Synthetic revenue-at-risk estimation using recoverability assumptions."""
    gross_failed_amount = 0.0
    estimated_recoverable_revenue = 0.0

    for row in rows:
        if str(row.get("status", "")).lower() != "failed":
            continue
        amount = float(row.get("amount", 0.0) or 0.0)
        gross_failed_amount += amount
        error_code = str(row.get("error_code") or "unknown").lower()
        recoverability = RECOVERABILITY_PROBABILITIES.get(error_code, 0.20)
        estimated_recoverable_revenue += amount * recoverability

    revenue_at_risk = estimated_recoverable_revenue
    return {
        "gross_failed_amount": round(gross_failed_amount, 2),
        "estimated_recoverable_revenue": round(estimated_recoverable_revenue, 2),
        "revenue_at_risk": round(revenue_at_risk, 2),
    }
