from __future__ import annotations

from typing import Any


def build_fingerprint(
    payment_method: str,
    provider: str,
    region: str,
    error_family: str,
    severity: str,
) -> str:
    return "|".join(
        [
            str(payment_method).upper(),
            str(provider).upper(),
            str(region).upper(),
            str(error_family).upper(),
            str(severity).upper(),
        ]
    )


def fingerprint_similarity(left: str, right: str) -> float:
    """Compare two canonical fingerprints using a simple weighted overlap score."""
    left_parts = str(left).split("|")
    right_parts = str(right).split("|")
    if len(left_parts) != len(right_parts):
        return 0.0

    matches = 0
    for a, b in zip(left_parts, right_parts):
        if a == b:
            matches += 1
    return round(matches / len(left_parts), 4)


def canonical_error_family(error_code: Any) -> str:
    code = str(error_code or "").upper()
    if "TIMEOUT" in code or "GATEWAY_TIMEOUT" in code or "UPI_TIMEOUT" in code:
        return "TIMEOUT"
    if "OUTAGE" in code or "NETWORK" in code:
        return "OUTAGE"
    if "CARD" in code or "FUNDS" in code or "AUTH" in code:
        return "CUSTOMER"
    return "UNKNOWN"
