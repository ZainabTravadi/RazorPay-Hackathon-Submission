"""Known incident cases for evaluating the investigation contract."""

SCENARIOS = [
    {"id": f"provider-outage-{index:02d}", "injected_incident": "provider_outage", "expected_root_cause": "provider_degradation", "expected_recovery_strategy": "provider_failover", "affected_dimension": "provider", "expected_severity": "critical", "expected_evidence": ["failure_rate", "latency_p95_ms"], "expected_historical_match": True}
    for index in range(1, 9)
] + [
    {"id": f"upi-degradation-{index:02d}", "injected_incident": "payment_method_degradation", "expected_root_cause": "payment_method_degradation", "expected_recovery_strategy": "alternative_method", "affected_dimension": "payment_method", "expected_severity": "high", "expected_evidence": ["failure_rate", "dominant_error_share"], "expected_historical_match": True}
    for index in range(1, 8)
] + [
    {"id": f"mixed-incident-{index:02d}", "injected_incident": "mixed_incident", "expected_root_cause": "provider_degradation", "expected_recovery_strategy": "provider_failover", "affected_dimension": "provider", "expected_severity": "critical", "expected_evidence": ["failure_rate", "dominant_error_share"], "expected_historical_match": True}
    for index in range(1, 6)
]


def evaluate(results: list[dict]) -> dict[str, float]:
    total = len(results) or 1
    correct = sum(item["predicted_root_cause"] == item["expected_root_cause"] for item in results)
    precise = sum(item.get("evidence_precision", 0) for item in results) / total
    false_diagnoses = sum(item["predicted_root_cause"] != item["expected_root_cause"] for item in results)
    return {"root_cause_accuracy": correct / total, "evidence_precision": precise, "false_diagnosis_rate": false_diagnoses / total,
            "average_tool_calls": sum(item.get("tool_call_count", 0) for item in results) / total,
            "average_investigation_time": sum(item.get("duration", 0) for item in results) / total}