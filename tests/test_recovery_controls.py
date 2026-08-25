from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from database.models import Incident, Payment
from database.session import SessionLocal


def _three_payment_recovery(client: TestClient) -> tuple[str, str]:
    client.post("/api/simulator/reset")
    injected = client.post("/api/simulator/inject/provider_outage").json()
    incident_id = injected["incident_id"]
    db = SessionLocal()
    try:
        incident = db.get(Incident, incident_id)
        incident.started_at = datetime.now(timezone.utc)
        incident.ended_at = None
        payments = list(db.scalars(select(Payment).where(Payment.payment_id.like(f"{incident_id}-%"))).all())
        candidates = [payment for payment in payments if payment.provider == incident.primary_provider and payment.payment_method == incident.primary_payment_method][:3]
        keep_ids = {payment.payment_id for payment in candidates}
        for payment in db.scalars(select(Payment)).all():
            if payment.payment_id not in keep_ids:
                payment.status = "captured"
        for payment in candidates:
            payment.status = "failed"
        db.commit()
    finally:
        db.close()
    recovery_id = client.post(f"/api/incidents/{incident_id}/recovery").json()["recovery_id"]
    assert client.post(f"/api/recoveries/{recovery_id}/approve").status_code == 200
    return incident_id, recovery_id


def _execute(client: TestClient, recovery_id: str, **policy: object) -> dict:
    response = client.post(f"/api/recoveries/{recovery_id}/execute", json=policy)
    assert response.status_code == 200, response.text
    return response.json()


def test_primary_success_has_one_attempt_and_no_fallback() -> None:
    with TestClient(app) as client:
        _, recovery_id = _three_payment_recovery(client)
        result = _execute(client, recovery_id, max_retries=0, fallback_strategy=None, primary_outcomes=["success"] * 3)
        attempts = client.get(f"/api/recoveries/{recovery_id}/attempts").json()
        events = client.get(f"/api/recoveries/{recovery_id}/events").json()
        assert result["execution_status"] == "completed"
        assert len(attempts) == 3
        assert {attempt["attempt_number"] for attempt in attempts} == {1}
        assert "FALLBACK_TRIGGERED" not in {event["event_type"] for event in events}


def test_primary_failure_executes_successful_fallback_and_uses_successful_ledger_only() -> None:
    with TestClient(app) as client:
        _, recovery_id = _three_payment_recovery(client)
        result = _execute(client, recovery_id, max_retries=0, fallback_strategy="alternative_method",
                          primary_outcomes=["failure"] * 3, fallback_outcomes=["success"] * 3)
        attempts = client.get(f"/api/recoveries/{recovery_id}/attempts").json()
        successful = [attempt for attempt in attempts if attempt["success"]]
        events = client.get(f"/api/recoveries/{recovery_id}/events").json()
        assert result["execution_status"] == "completed"
        assert len(attempts) == 6
        assert len(successful) == 3
        assert all(attempt["attempt_number"] == 1 for attempt in attempts[:3])
        assert all(attempt["attempt_number"] == 2 for attempt in attempts[3:])
        assert {event["event_type"] for event in events} >= {"ATTEMPT_FAILED", "FALLBACK_TRIGGERED", "PAYMENT_RECOVERED"}
        assert result["recovered_revenue"] == round(sum(attempt["amount"] for attempt in successful) * 0.18, 2)


def test_fallback_failure_escalates_and_is_a_hard_stop() -> None:
    with TestClient(app) as client:
        incident_id, recovery_id = _three_payment_recovery(client)
        result = _execute(client, recovery_id, max_retries=0, fallback_strategy="alternative_method",
                          primary_outcomes=["failure"], fallback_outcomes=["failure"])
        attempts_before = client.get(f"/api/recoveries/{recovery_id}/attempts").json()
        events = client.get(f"/api/recoveries/{recovery_id}/events").json()
        assert result["execution_status"] == "escalated"
        assert result["triggering_rule"] == "FALLBACK_FAILED"
        assert len(attempts_before) == 2
        assert "RECOVERY_ESCALATED" in {event["event_type"] for event in events}
        replay = client.get(f"/api/incidents/{incident_id}/replay").json()
        replay_types = {event["type"] for event in replay["events"]}
        assert {"ATTEMPT_FAILED", "FALLBACK_TRIGGERED", "RECOVERY_ESCALATED"} <= replay_types
        assert client.post(f"/api/recoveries/{recovery_id}/execute", json={}).status_code == 404
        assert len(client.get(f"/api/recoveries/{recovery_id}/attempts").json()) == len(attempts_before)


def test_failure_rate_threshold_blocks_further_automation() -> None:
    with TestClient(app) as client:
        _, recovery_id = _three_payment_recovery(client)
        result = _execute(client, recovery_id, max_retries=0, fallback_strategy=None,
                          failure_rate_threshold=0.5, primary_outcomes=["failure"] * 3)
        events = client.get(f"/api/recoveries/{recovery_id}/events").json()
        assert result["execution_status"] == "blocked"
        assert result["triggering_rule"] == "FAILURE_RATE_THRESHOLD"
        assert len(client.get(f"/api/recoveries/{recovery_id}/attempts").json()) == 2
        assert any(event["event_type"] == "STOPPING_RULE_TRIGGERED" and event["metadata_json"]["rule"] == "FAILURE_RATE_THRESHOLD" for event in events)


def test_expired_recovery_window_is_rejected_before_attempts() -> None:
    with TestClient(app) as client:
        _, recovery_id = _three_payment_recovery(client)
        result = _execute(client, recovery_id, recovery_window_seconds=0)
        assert result["execution_status"] == "blocked"
        assert result["triggering_rule"] == "RECOVERY_TIME_WINDOW"
        assert client.get(f"/api/recoveries/{recovery_id}/attempts").json() == []


def test_retry_budget_is_bounded_and_escalates_after_last_retry() -> None:
    with TestClient(app) as client:
        _, recovery_id = _three_payment_recovery(client)
        result = _execute(client, recovery_id, max_retries=2, fallback_strategy=None,
                          primary_outcomes=["failure"] * 3)
        attempts = client.get(f"/api/recoveries/{recovery_id}/attempts").json()
        assert result["execution_status"] == "escalated"
        assert result["triggering_rule"] == "MAX_RETRIES"
        assert max(attempt["attempt_number"] for attempt in attempts) == 3
        first_payment_id = attempts[0]["payment_id"]
        assert [attempt["attempt_number"] for attempt in attempts if attempt["payment_id"] == first_payment_id] == [1, 2, 3]
        assert all(attempt["attempt_number"] <= 3 for attempt in attempts)
        assert client.post(f"/api/recoveries/{recovery_id}/execute", json={}).status_code == 404


def test_duplicate_payment_is_recovered_once_and_replay_keeps_event_order() -> None:
    with TestClient(app) as client:
        incident_id, recovery_id = _three_payment_recovery(client)
        result = _execute(client, recovery_id, max_retries=0, fallback_strategy=None, primary_outcomes=["success"] * 3)
        attempts = client.get(f"/api/recoveries/{recovery_id}/attempts").json()
        replay = client.get(f"/api/incidents/{incident_id}/replay").json()
        successful_ids = [attempt["payment_id"] for attempt in attempts if attempt["success"]]
        assert len(successful_ids) == len(set(successful_ids)) == 3
        assert result["recovered_transactions"] == 3
        assert result["recovered_revenue"] <= result["before_metrics"]["revenue_at_risk"]
        assert [event["timestamp"] for event in replay["events"]] == sorted(event["timestamp"] for event in replay["events"])
