from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")

_PROVIDER_ALIASES = {"p1": "provider_a", "p2": "provider_b", "p3": "provider_c"}
_PROVIDERS = {
    "provider_a": {"provider_id": "provider_a", "provider_name": "Provider A", "baseline_success_rate": 0.96, "health_status": "healthy"},
    "provider_b": {"provider_id": "provider_b", "provider_name": "Provider B", "baseline_success_rate": 0.93, "health_status": "degraded"},
    "provider_c": {"provider_id": "provider_c", "provider_name": "Provider C", "baseline_success_rate": 0.95, "health_status": "healthy"},
}


@router.get("/providers")
def list_providers() -> list[dict]:
    return list(_PROVIDERS.values())


@router.get("/providers/{provider_id}/health")
def provider_health(provider_id: str) -> dict:
    canonical_id = _PROVIDER_ALIASES.get(provider_id, provider_id)
    provider = _PROVIDERS.get(canonical_id)
    if provider is None:
        return {"provider_id": provider_id, "health_status": "unknown", "synthetic": True}
    return {**provider, "synthetic": True}
