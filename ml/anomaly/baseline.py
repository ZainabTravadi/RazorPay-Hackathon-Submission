from __future__ import annotations

from typing import Any

import pandas as pd


def _safe_zscore(current: float, baseline: float, std: float) -> float:
    if pd.isna(std) or std == 0:
        return 0.0
    return float((current - baseline) / std)


def compute_metric_baseline(
    df: pd.DataFrame,
    *,
    dimension: str,
    metric: str,
    current_value: float,
    entity: str,
) -> tuple[float, float, float]:
    """Return baseline, standard deviation, and z-score for a single metric/entity pair."""
    grouped = df.groupby(dimension, dropna=False)
    series = grouped.apply(lambda g: {
        "failure_rate": float((g["status"] == "failed").mean()),
        "success_rate": float(g["status"].isin(["captured", "authorized"]).mean()),
        "timeout_rate": float(g["error_code"].fillna("").str.contains("timeout|outage|network", case=False, regex=True).mean()),
        "latency": float(g["latency_ms"].mean()),
    }).apply(pd.Series)

    if metric not in series.columns:
        return current_value, 0.0, 0.0

    if entity not in series.index:
        return current_value, 0.0, 0.0

    baseline = float(series[metric].mean())
    std = float(series[metric].std(ddof=0))
    z_score = _safe_zscore(current_value, baseline, std)
    return baseline, std, z_score
