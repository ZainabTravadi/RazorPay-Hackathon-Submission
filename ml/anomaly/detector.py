from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ml.anomaly.baseline import compute_metric_baseline
from ml.fingerprinting.fingerprint import build_fingerprint, canonical_error_family


def _severity_for_score(score: float) -> str:
    if abs(score) >= 6.0:
        return "critical"
    if abs(score) >= 4.0:
        return "high"
    if abs(score) >= 2.5:
        return "medium"
    return "low"


def detect_anomalies(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return structured anomaly records for payment health metrics."""
    if df.empty:
        return []

    dff = df.copy()
    dff["status"] = dff["status"].fillna("unknown")
    dff["error_code"] = dff["error_code"].fillna("")
    dff["timestamp"] = pd.to_datetime(dff["timestamp"])

    results: list[dict[str, Any]] = []
    dimensions = ["provider", "payment_method", "region"]

    for dimension in dimensions:
        grouped = dff.groupby(dimension, dropna=False)
        overall_failure_rate = float(dff["status"].eq("failed").mean())
        overall_success_rate = float(dff["status"].isin(["captured", "authorized"]).mean())
        overall_timeout_rate = float(dff["error_code"].str.contains("timeout|outage|network", case=False, regex=True).mean())
        overall_latency = float(dff["latency_ms"].mean())

        for entity, group in grouped:
            total = len(group)
            if total < 25:
                continue

            failure_rate = float((group["status"] == "failed").mean())
            success_rate = float(group["status"].isin(["captured", "authorized"]).mean())
            latency = float(group["latency_ms"].mean())
            timeout_rate = float(group["error_code"].str.contains("timeout|outage|network", case=False, regex=True).mean())

            metric_set = [
                ("failure_rate", failure_rate, overall_failure_rate, max(0.05, overall_failure_rate * 0.3)),
                ("success_rate", success_rate, overall_success_rate, max(0.05, overall_success_rate * 0.3)),
                ("timeout_rate", timeout_rate, overall_timeout_rate, max(0.05, overall_timeout_rate * 0.3)),
                ("latency", latency, overall_latency, max(150.0, overall_latency * 0.3)),
            ]

            for metric, current_value, baseline_value, std_value in metric_set:
                if std_value <= 0:
                    continue
                z_score = float((current_value - baseline_value) / std_value)

                threshold = False
                if metric == "failure_rate":
                    threshold = current_value >= max(0.70, baseline_value + 0.25)
                elif metric == "success_rate":
                    threshold = current_value <= min(0.70, baseline_value - 0.20)
                elif metric == "timeout_rate":
                    threshold = current_value >= max(0.60, baseline_value + 0.25)
                elif metric == "latency":
                    threshold = current_value >= max(1800.0, baseline_value * 1.8)

                if not threshold:
                    continue

                severity = _severity_for_score(z_score)
                results.append(
                    {
                        "dimension": dimension,
                        "entity": str(entity),
                        "metric": metric,
                        "current_value": round(float(current_value), 4),
                        "baseline_value": round(float(baseline_value), 4),
                        "z_score": round(float(z_score), 4),
                        "severity": severity,
                        "is_anomaly": True,
                    }
                )

    return results


def detect_incidents(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Combine anomaly signals into payment incidents."""
    anomalies = detect_anomalies(df)
    incidents: list[dict[str, Any]] = []
    if not anomalies:
        return incidents

    unique_anomaly_keys = {}
    for anomaly in anomalies:
        key = (anomaly["dimension"], anomaly["entity"])
        unique_anomaly_keys[key] = anomaly

    for anomaly in unique_anomaly_keys.values():
        metric = anomaly["metric"]
        group = df[df[anomaly["dimension"]] == anomaly["entity"]]
        if group.empty:
            continue

        if anomaly["dimension"] == "provider":
            incident_type = "provider_outage" if anomaly["metric"] == "failure_rate" and anomaly["current_value"] > 0.45 else "provider_latency_spike"
            primary_payment_method = str(group["payment_method"].mode().iloc[0]) if not group["payment_method"].mode().empty else "UPI"
            primary_region = str(group["region"].mode().iloc[0]) if not group["region"].mode().empty else "Mumbai"
        elif anomaly["dimension"] == "payment_method":
            incident_type = "payment_method_degradation"
            primary_payment_method = anomaly["entity"]
            primary_region = str(group["region"].mode().iloc[0]) if not group["region"].mode().empty else "Mumbai"
        else:
            incident_type = "regional_degradation"
            primary_payment_method = str(group["payment_method"].mode().iloc[0]) if not group["payment_method"].mode().empty else "UPI"
            primary_region = anomaly["entity"]

        incident = {
            "incident_id": f"INC-{len(incidents) + 1:04d}",
            "incident_type": incident_type,
            "severity": anomaly["severity"],
            "status": "detected",
            "started_at": group["timestamp"].min().isoformat(),
            "ended_at": None,
            "detected_at": group["timestamp"].max().isoformat(),
            "anomaly_score": round(float(abs(anomaly["z_score"])), 2),
            "affected_transactions": int(len(group)),
            "affected_merchants": int(group["merchant_id"].nunique()),
            "revenue_at_risk": round(float(group["amount"].sum() * (0.25 if "failure" in metric else 0.2)), 2),
            "primary_provider": str(group["provider"].mode().iloc[0]) if not group["provider"].mode().empty else anomaly["entity"],
            "primary_payment_method": primary_payment_method,
            "primary_region": primary_region,
            "fingerprint": build_fingerprint(
                primary_payment_method,
                str(group["provider"].mode().iloc[0]) if not group["provider"].mode().empty else anomaly["entity"],
                primary_region,
                canonical_error_family(group["error_code"].mode().iloc[0] if not group["error_code"].mode().empty else "TIMEOUT"),
                anomaly["severity"],
            ),
            "description": f"Anomaly detected in {anomaly['dimension']} {anomaly['entity']} for {metric}.",
        }
        incidents.append(incident)

    return incidents
