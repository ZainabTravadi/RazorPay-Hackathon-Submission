from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app
from evaluation.benchmark import SCENARIOS


def run() -> dict:
    rows = []
    with TestClient(app) as client:
        for scenario in SCENARIOS:
            client.post("/api/simulator/reset")
            injected = client.post(f"/api/simulator/inject/{scenario['injected_incident']}").json()
            started = time.perf_counter(); investigation = client.post(f"/api/investigate/{injected['incident_id']}").json(); elapsed = (time.perf_counter() - started) * 1000
            result = investigation["final_result"]
            recommendation = client.get(f"/api/incidents/{injected['incident_id']}/recovery-recommendation").json()
            rows.append({"scenario": scenario["id"], "expected_root_cause": scenario["expected_root_cause"], "predicted_root_cause": result["root_cause_category"],
                         "classification_correct": result["root_cause_category"] == scenario["expected_root_cause"], "expected_recovery_strategy": scenario["expected_recovery_strategy"],
                         "recovery_strategy": recommendation["strategy"], "recovery_correct": recommendation["strategy"] == scenario["expected_recovery_strategy"],
                         "tool_call_count": result["tool_call_count"], "duration": elapsed})
    total = len(rows)
    report = {"total_scenarios": total, "root_cause_accuracy": sum(row["classification_correct"] for row in rows) / total,
              "classification_accuracy": sum(row["classification_correct"] for row in rows) / total,
              "recovery_recommendation_accuracy": sum(row["recovery_correct"] for row in rows) / total, "false_positive_rate": None,
              "average_tool_calls": sum(row["tool_call_count"] for row in rows) / total,
              "average_investigation_time_ms": sum(row["duration"] for row in rows) / total, "scenarios": rows}
    Path("evaluation/report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))