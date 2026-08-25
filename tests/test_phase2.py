from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.services.investigation_tools import TOOLS, call_tool
from apps.api.services.investigator import evidence_confidence


def test_read_only_tool_registry_has_ten_tools() -> None:
    assert len(TOOLS) == 10
    assert not any(word in TOOLS for word in ("refund", "retry", "route", "update"))


def test_confidence_is_reproducible_and_bounded() -> None:
    value = evidence_confidence(8, 4, .9, .8, .1)
    assert value == evidence_confidence(8, 4, .9, .8, .1)
    assert 0 <= value <= 1


def test_unknown_tool_is_rejected() -> None:
    try:
        call_tool(None, "refund_payment", incident_id="INC-1")
    except ValueError as error:
        assert "read-only" in str(error)
    else:
        raise AssertionError("mutation tool was accepted")


def test_mock_investigation_persists_trace() -> None:
    client = TestClient(app)
    client.post("/api/simulator/reset")
    injected = client.post("/api/simulator/inject/provider_outage").json()
    first = client.post(f"/api/investigate/{injected['incident_id']}")
    assert first.status_code == 200
    payload = first.json()
    assert payload["final_result"]["confidence"] > 0
    assert payload["final_result"]["tool_call_count"] <= 12
    assert len(client.get(f"/api/investigations/{payload['investigation_id']}/trace").json()) == 8


def test_rca_graph_exposes_existing_reasoning_chain() -> None:
    with TestClient(app) as client:
        client.post("/api/simulator/reset")
        incident_id = client.post("/api/simulator/inject/provider_outage").json()["incident_id"]
        assert client.post(f"/api/investigate/{incident_id}").status_code == 200

        response = client.get(f"/api/incidents/{incident_id}/rca-graph")
        assert response.status_code == 200
        payload = response.json()

        assert payload["incident_id"] == incident_id
        assert isinstance(payload["nodes"], list)
        assert isinstance(payload["edges"], list)
        assert len(payload["nodes"]) > 0
        assert len(payload["edges"]) > 0
        assert all({"id", "label", "type"} <= set(node) for node in payload["nodes"])
        assert all({"source", "target", "relationship"} <= set(edge) for edge in payload["edges"])


def test_recovery_requires_approval_and_does_not_mutate_payments() -> None:
    with TestClient(app) as client:
        client.post("/api/simulator/reset")
        injected = client.post("/api/simulator/inject/provider_outage").json()
        incident_id = injected["incident_id"]
        before = client.get("/api/payments?limit=5000").json()["count"]
        recommendation = client.post(f"/api/incidents/{incident_id}/recovery")
        assert recommendation.status_code == 200
        pending = recommendation.json()
        assert pending["approval_status"] == "pending"
        assert client.post(f"/api/recoveries/{pending['recovery_id']}/execute").status_code == 403
        result = client.post(f"/api/recoveries/{pending['recovery_id']}/approve")
        assert result.status_code == 200
        assert result.json()["simulation"] is True
        assert result.json()["approval_status"] == "approved"
        assert result.json()["execution_status"] == "not_started"
        completed = client.post(f"/api/recoveries/{pending['recovery_id']}/execute")
        assert completed.status_code == 200
        assert completed.json()["execution_status"] == "completed"
        assert client.get("/api/payments?limit=5000").json()["count"] == before


def test_rejection_and_duplicate_actions_are_blocked() -> None:
    with TestClient(app) as client:
        client.post("/api/simulator/reset")
        incident_id = client.post("/api/simulator/inject/provider_outage").json()["incident_id"]
        recovery_id = client.post(f"/api/incidents/{incident_id}/recovery").json()["recovery_id"]
        assert client.post(f"/api/recoveries/{recovery_id}/reject").status_code == 200
        assert client.post(f"/api/recoveries/{recovery_id}/approve").status_code == 404
        assert client.get("/api/incidents/does-not-exist/impact").status_code == 404
        assert client.post("/api/recoveries/does-not-exist/approve").status_code == 404
