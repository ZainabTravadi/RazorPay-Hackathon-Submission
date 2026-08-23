from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_summary(client) -> None:
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert "payment_success_rate" in payload
    assert "failure_rate" in payload


def test_historical_incidents_endpoint(client) -> None:
    response = client.get("/api/historical-incidents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_providers_endpoint(client) -> None:
    response = client.get("/api/providers")
    assert response.status_code == 200
    assert len(response.json()) >= 3


def test_reset_then_inject_provider_outage(client) -> None:
    reset = client.post("/api/simulator/reset")
    assert reset.status_code == 200
    inject = client.post("/api/simulator/inject/provider_outage")
    assert inject.status_code == 200
    incidents_response = client.get("/api/incidents")
    assert incidents_response.status_code == 200
    payload = incidents_response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
