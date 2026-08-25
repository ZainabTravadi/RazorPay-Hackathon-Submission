from fastapi.testclient import TestClient

from apps.api.main import app


def _incident(client: TestClient) -> str:
    client.post("/api/simulator/reset")
    return client.post("/api/simulator/inject/provider_outage").json()["incident_id"]


def test_incident_recovery_returns_persisted_execution_and_outcome() -> None:
    with TestClient(app) as client:
        incident_id = _incident(client)
        prepared = client.post(f"/api/incidents/{incident_id}/recovery").json()
        recovery_id = prepared["recovery_id"]
        assert client.post(f"/api/recoveries/{recovery_id}/approve").status_code == 200
        executed = client.post(f"/api/recoveries/{recovery_id}/execute").json()

        response = client.get(f"/api/incidents/{incident_id}/recovery")
        assert response.status_code == 200
        recovered = response.json()
        assert recovered["recovery_id"] == recovery_id
        assert recovered["strategy"] == executed["strategy"]
        assert recovered["approval_status"] == "approved"
        assert recovered["execution_status"] == "completed"
        assert recovered["recovered_transactions"] == executed["recovered_transactions"]
        assert recovered["recovered_revenue"] == executed["recovered_revenue"]
        assert "max_retries" in recovered
        assert "failure_rate_threshold" in recovered
        assert "recovery_window_seconds" in recovered
        assert client.get(f"/api/recoveries/{recovery_id}/attempts").status_code == 200
        assert client.get(f"/api/recoveries/{recovery_id}/events").status_code == 200


def test_incident_recovery_returns_not_found_when_no_recovery_exists() -> None:
    with TestClient(app) as client:
        incident_id = _incident(client)
        response = client.get(f"/api/incidents/{incident_id}/recovery")
        assert response.status_code == 404
        assert response.json()["detail"] == "Recovery not found"


def test_incident_recovery_selects_latest_persisted_record() -> None:
    with TestClient(app) as client:
        incident_id = _incident(client)
        first = client.post(f"/api/incidents/{incident_id}/recovery").json()
        assert client.post(f"/api/recoveries/{first['recovery_id']}/reject").status_code == 200
        second = client.post(f"/api/incidents/{incident_id}/recovery").json()

        response = client.get(f"/api/incidents/{incident_id}/recovery")
        assert response.status_code == 200
        assert response.json()["recovery_id"] == second["recovery_id"]
        assert response.json()["approval_status"] == "pending"
