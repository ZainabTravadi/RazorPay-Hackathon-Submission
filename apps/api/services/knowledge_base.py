from __future__ import annotations

DOCUMENTS = [
    ("upi-timeouts", "UPI timeout troubleshooting", "UPI timeout concentration with provider-specific latency indicates provider degradation. Compare provider health with regional and method-wide rates before routing decisions."),
    ("card-auth", "Card authorization failures", "Card authorization errors should be separated from infrastructure failures. Check error distribution and authorization response patterns."),
    ("provider-latency", "Provider latency", "A provider p95 latency spike plus elevated failure rate is stronger evidence of provider degradation than either metric alone."),
    ("webhooks", "Webhook failures", "Webhook delivery failures affect reconciliation after authorization. They do not by themselves prove payment authorization failure."),
    ("pending", "Payment pending states", "Pending payments require timeline review and should not be retried blindly."),
    ("refunds", "Refund failures", "Refund errors are separate from capture failures and require a distinct recovery workflow."),
    ("outage", "Provider outage handling", "Confirm impact across providers and regions. Recovery recommendations are informational until an operator approves them."),
    ("merchant-config", "Merchant configuration errors", "Merchant-scoped failures suggest configuration issues; broad provider-scoped failures suggest infrastructure."),
    ("retry-safety", "Retry safety", "Never retry an unknown payment state without idempotency protection."),
    ("duplicates", "Duplicate payment risks", "Repeated retries can create duplicate captures; investigation tools must remain read-only."),
]


def search_knowledge(query: str, limit: int = 5) -> list[dict[str, str]]:
    terms = set(query.lower().split())
    ranked = sorted(DOCUMENTS, key=lambda item: len(terms & set((item[1] + " " + item[2]).lower().split())), reverse=True)
    return [{"document_id": item[0], "title": item[1], "content": item[2]} for item in ranked[:limit]]