from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from apps.api.main import app
from database.models import HistoricalIncident
from database.session import SessionLocal


def _prepare_incident(client: TestClient) -> tuple[str, dict]:
    client.post("/api/simulator/reset")
    injected = client.post("/api/simulator/inject/provider_outage")
    assert injected.status_code == 200
    incident_id = injected.json()["incident_id"]
    assert client.post(f"/api/investigate/{incident_id}").status_code == 200
    return incident_id, injected.json()


def _prepare_recovery(client: TestClient, incident_id: str) -> dict:
    prepared = client.post(f"/api/incidents/{incident_id}/recovery")
    assert prepared.status_code == 200
    payload = prepared.json()
    assert payload["approval_status"] == "pending"
    assert payload["execution_status"] == "not_started"
    approved = client.post(f"/api/recoveries/{payload['recovery_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"
    assert approved.json()["execution_status"] == "not_started"
    completed = client.post(f"/api/recoveries/{payload['recovery_id']}/execute")
    assert completed.status_code == 200
    assert completed.json()["execution_status"] == "completed"
    return completed.json()


def test_replay_is_chronological_and_deterministic() -> None:
    with TestClient(app) as client:
        incident_id, _ = _prepare_incident(client)
        first = client.get(f"/api/incidents/{incident_id}/replay")
        second = client.get(f"/api/incidents/{incident_id}/replay")

        assert first.status_code == 200
        assert second.status_code == 200
        payload = first.json()
        assert payload == second.json()
        assert payload["incident"]["incident_id"].startswith("INC-")
        assert payload["incident"]["source_kind"] == "incident"

        events = payload["events"]
        assert len(events) >= 5
        assert [event["event_id"] for event in events] == [event["event_id"] for event in second.json()["events"]]
        assert len({event["event_id"] for event in events}) == len(events)
        assert [event["timestamp"] for event in events] == sorted(event["timestamp"] for event in events)
        assert any((event.get("investigation_id") or "").startswith("INV-") for event in events)
        assert all(event["incident_id"].startswith("INC-") for event in events)


def test_replay_does_not_mutate_incident_or_recovery_state() -> None:
    with TestClient(app) as client:
        incident_id, _ = _prepare_incident(client)
        before_incident = client.get(f"/api/incidents/{incident_id}").json()
        before_investigations = client.get("/api/investigations").json()

        replay = client.get(f"/api/incidents/{incident_id}/replay")
        assert replay.status_code == 200
        assert client.get(f"/api/incidents/{incident_id}").json() == before_incident
        assert client.get("/api/investigations").json() == before_investigations


def test_replay_does_not_mutate_existing_recovery_state() -> None:
    with TestClient(app) as client:
        incident_id, _ = _prepare_incident(client)
        before_recovery = _prepare_recovery(client, incident_id)

        replay = client.get(f"/api/incidents/{incident_id}/replay")
        assert replay.status_code == 200
        payload = replay.json()

        assert payload["has_recovery"] is True
        assert any(event["type"] == "RECOVERY_APPROVED" for event in payload["events"])
        assert any(event["type"] == "RECOVERY_EXECUTED" for event in payload["events"])
        assert client.post(f"/api/recoveries/{before_recovery['recovery_id']}/approve").status_code == 404
        assert client.post(f"/api/recoveries/{before_recovery['recovery_id']}/execute").status_code == 404


def test_replay_event_endpoint_matches_timeline() -> None:
    with TestClient(app) as client:
        incident_id, _ = _prepare_incident(client)
        replay = client.get(f"/api/incidents/{incident_id}/replay").json()
        event = replay["events"][0]
        detail = client.get(f"/api/incidents/{incident_id}/replay/{event['event_id']}")

        assert detail.status_code == 200
        assert detail.json() == event


def test_historical_incident_replay_is_available() -> None:
    with TestClient(app) as client:
        historical = client.get("/api/historical-incidents").json()
        if not historical:
            db = SessionLocal()
            try:
                db.merge(
                    HistoricalIncident(
                        incident_id="HIST-REPLAY-TEST",
                        incident_type="provider_outage",
                        fingerprint="CARD|PROVIDER B|MUMBAI|OUTAGE|HIGH",
                        root_cause="Provider outage",
                        resolution="Provider routing restored",
                        recovery_rate=0.92,
                        revenue_impact=128000.0,
                        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                    )
                )
                db.commit()
            finally:
                db.close()
            historical = client.get("/api/historical-incidents").json()

        assert historical
        incident_id = historical[0]["incident_id"]
        response = client.get(f"/api/incidents/{incident_id}/replay")
        assert response.status_code == 200
        payload = response.json()
        assert payload["incident"]["source_kind"] == "historical"
        assert payload["event_count"] >= 1
        assert payload["events"][0]["event_id"].startswith(f"RPL-{incident_id}")


def test_missing_replay_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/incidents/does-not-exist/replay")
        assert response.status_code == 404
