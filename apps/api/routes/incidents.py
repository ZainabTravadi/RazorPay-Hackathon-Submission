from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.schemas.investigation import InvestigationResult
from apps.api.services.incident_service import list_active_incidents, get_incident_by_id
from apps.api.services.investigation_tools import get_failure_clusters, get_transaction_timeline
from database.models import Investigation
from database.session import get_db

router = APIRouter(prefix="/api")


@router.get("/incidents")
def list_incidents(db: Session = Depends(get_db)) -> list[dict]:
    incidents = list_active_incidents(db)
    return [
        {
            "incident_id": item.incident_id,
            "incident_type": item.incident_type,
            "severity": item.severity,
            "status": item.status,
            "started_at": item.started_at.isoformat() if item.started_at else None,
            "ended_at": item.ended_at.isoformat() if item.ended_at else None,
            "detected_at": item.detected_at.isoformat() if item.detected_at else None,
            "anomaly_score": item.anomaly_score,
            "affected_transactions": item.affected_transactions,
            "affected_merchants": item.affected_merchants,
            "revenue_at_risk": item.revenue_at_risk,
            "primary_provider": item.primary_provider,
            "primary_payment_method": item.primary_payment_method,
            "primary_region": item.primary_region,
            "fingerprint": item.fingerprint,
            "description": item.description,
        }
        for item in incidents
    ]


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, db: Session = Depends(get_db)) -> dict:
    incident = get_incident_by_id(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {
        "incident_id": incident.incident_id,
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "status": incident.status,
        "started_at": incident.started_at.isoformat() if incident.started_at else None,
        "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
        "detected_at": incident.detected_at.isoformat() if incident.detected_at else None,
        "anomaly_score": incident.anomaly_score,
        "affected_transactions": incident.affected_transactions,
        "affected_merchants": incident.affected_merchants,
        "revenue_at_risk": incident.revenue_at_risk,
        "primary_provider": incident.primary_provider,
        "primary_payment_method": incident.primary_payment_method,
        "primary_region": incident.primary_region,
        "fingerprint": incident.fingerprint,
        "description": incident.description,
    }


@router.get("/incidents/{incident_id}/clusters")
def incident_clusters(incident_id: str, db: Session = Depends(get_db)) -> list[dict]:
    try:
        clusters = get_failure_clusters(db, incident_id)["clusters"]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [{"cluster_id": f"CL-{incident_id}-{index}", **cluster} for index, cluster in enumerate(clusters, start=1)]


@router.get("/incidents/{incident_id}/fingerprint")
def incident_fingerprint(incident_id: str, db: Session = Depends(get_db)) -> dict:
    incident = get_incident_by_id(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident_id": incident_id, "fingerprint": incident.fingerprint, "synthetic": True}


@router.get("/incidents/{incident_id}/timeline")
def incident_timeline(incident_id: str, db: Session = Depends(get_db)) -> list[dict]:
    try:
        return get_transaction_timeline(db, incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _latest_investigation_result(db: Session, incident_id: str) -> InvestigationResult | None:
    row = db.scalars(
        select(Investigation)
        .where(Investigation.incident_id == incident_id)
        .order_by(Investigation.started_at.desc())
    ).first()
    if row is None:
        return None
    return InvestigationResult.model_validate_json(row.result_json)


def _build_rca_graph(incident, result: InvestigationResult) -> dict:
    nodes = [{"id": incident.incident_id, "label": incident.description or incident.incident_id, "type": "incident"}]
    edges = []

    evidence_nodes = []
    for index, evidence in enumerate(result.evidence, start=1):
        node_id = f"{incident.incident_id}:evidence:{index}"
        nodes.append({"id": node_id, "label": evidence.description, "type": "evidence"})
        edges.append({"source": incident.incident_id, "target": node_id, "relationship": "observed"})
        evidence_nodes.append(node_id)

    hypothesis_nodes = []
    for index, hypothesis in enumerate(result.alternative_hypotheses, start=1):
        node_id = f"{incident.incident_id}:hypothesis:{index}"
        nodes.append({"id": node_id, "label": hypothesis.hypothesis, "type": "hypothesis"})
        hypothesis_nodes.append(node_id)
        for evidence_node in evidence_nodes:
            edges.append({"source": evidence_node, "target": node_id, "relationship": "supports"})

    root_cause_id = f"{incident.incident_id}:root-cause"
    nodes.append({"id": root_cause_id, "label": result.root_cause, "type": "root_cause"})
    for hypothesis_node in hypothesis_nodes:
        edges.append({"source": hypothesis_node, "target": root_cause_id, "relationship": "converges_on"})

    action_id = f"{incident.incident_id}:recovery-action"
    nodes.append({"id": action_id, "label": result.recommended_next_step, "type": "recovery_action"})
    edges.append({"source": root_cause_id, "target": action_id, "relationship": "leads_to"})
    return {"nodes": nodes, "edges": edges}


@router.get("/incidents/{incident_id}/rca-graph")
def incident_rca_graph(incident_id: str, db: Session = Depends(get_db)) -> dict:
    incident = get_incident_by_id(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    result = _latest_investigation_result(db, incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    graph = _build_rca_graph(incident, result)
    return {"incident_id": incident_id, **graph}
