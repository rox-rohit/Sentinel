"""Exploratory data analysis generated from the selected dataset.

No statistics or chart data are hardcoded: every number here is computed from
the canonical frame passed in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sentinel.data.schema import DatasetSchema


@dataclass
class EDAResult:
    payload: dict


def descriptive_table(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    rows = []
    for column in columns:
        if column not in df.columns:
            continue
        series = df[column].dropna()
        if series.empty:
            continue
        rows.append({
            "column": column,
            "count": int(series.count()),
            "mean": round(float(series.mean()), 4),
            "std": round(float(series.std()), 4),
            "min": round(float(series.min()), 4),
            "p25": round(float(series.quantile(0.25)), 4),
            "median": round(float(series.median()), 4),
            "p75": round(float(series.quantile(0.75)), 4),
            "max": round(float(series.max()), 4),
            "skew": round(float(series.skew()), 4),
            "missing": int(df[column].isna().sum()),
        })
    return rows


def correlation_matrix(df: pd.DataFrame, columns: list[str]) -> dict:
    available = [c for c in columns if c in df.columns]
    corr = df[available].corr(numeric_only=True).round(3)
    return {
        "features": available,
        "matrix": corr.fillna(0.0).to_numpy().tolist(),
    }


def top_correlations(df: pd.DataFrame, columns: list[str], limit: int = 8) -> list[dict]:
    available = [c for c in columns if c in df.columns]
    corr = df[available].corr(numeric_only=True).abs()
    pairs = []
    seen = set()
    for i, a in enumerate(available):
        for b in available[i + 1:]:
            value = corr.loc[a, b]
            if not np.isfinite(value):
                continue
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"a": a, "b": b, "abs_correlation": round(float(value), 3)})
    pairs.sort(key=lambda row: row["abs_correlation"], reverse=True)
    return pairs[:limit]


def histograms(df: pd.DataFrame, columns: list[str], bins: int = 12) -> list[dict]:
    out = []
    for column in columns:
        if column not in df.columns:
            continue
        series = df[column].dropna()
        if series.empty or series.nunique() < 2:
            continue
        counts, edges = np.histogram(series, bins=bins)
        out.append({
            "column": column,
            "counts": [int(c) for c in counts],
            "edges": [round(float(e), 3) for e in edges],
            "mean": round(float(series.mean()), 3),
        })
    return out


def degradation_curves(df: pd.DataFrame, sensors: list[str], *, group_col: str,
                       time_col: str, points: int = 20) -> list[dict]:
    """Mean sensor value by normalised life decile, per sensor."""
    if group_col not in df.columns:
        return []
    frame = df.copy()
    last = frame.groupby(group_col)[time_col].transform("max")
    first = frame.groupby(group_col)[time_col].transform("min")
    span = (last - first).replace(0, np.nan)
    frame["life_fraction"] = ((frame[time_col] - first) / span).clip(0, 1)
    frame["bin"] = (frame["life_fraction"] * points).clip(0, points - 1).round().astype(int)
    curves = []
    for sensor in sensors:
        if sensor not in frame.columns:
            continue
        grouped = frame.groupby("bin")[sensor].mean()
        curves.append({
            "sensor": sensor,
            "life_fraction": [round(b / (points - 1), 3) for b in grouped.index],
            "mean_value": [round(float(v), 4) for v in grouped.to_numpy()],
        })
    return curves


def machine_comparison(df: pd.DataFrame, *, group_col: str, sensor: str,
                       time_col: str | None = None) -> list[dict]:
    """Per-unit summary: latest value, lifetime mean and recorded lifetime."""
    if group_col not in df.columns or sensor not in df.columns:
        return []
    rows = []
    for unit, group in df.groupby(group_col, sort=True):
        ordered = group.sort_values(time_col) if time_col else group
        rows.append({
            "unit": str(unit),
            "latest": round(float(ordered[sensor].iloc[-1]), 4),
            "mean": round(float(group[sensor].mean()), 4),
            "lifetime": int(group[time_col].max()) if time_col else int(len(group)),
        })
    rows.sort(key=lambda row: row["latest"], reverse=True)
    return rows


def build_eda(df: pd.DataFrame, schema: DatasetSchema, *, max_sensors: int = 10) -> EDAResult:
    sensors = [s for s in schema.sensor_columns if s in df.columns][:max_sensors]
    payload = {
        "dataset": schema.name,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "descriptive": descriptive_table(df, sensors),
        "correlation": correlation_matrix(df, sensors),
        "top_correlations": top_correlations(df, sensors),
        "histograms": histograms(df, sensors),
        "missing": [
            {"column": c, "missing": int(df[c].isna().sum()),
             "pct": round(float(df[c].isna().mean() * 100), 3)}
            for c in sensors
        ],
    }
    if schema.time_column:
        payload["degradation"] = degradation_curves(
            df, sensors[:4], group_col=schema.id_column, time_col=schema.time_column
        )
        payload["machine_comparison"] = machine_comparison(
            df, group_col=schema.id_column, sensor=sensors[0], time_col=schema.time_column
        )
        payload["fleet_size"] = int(df[schema.id_column].nunique())
    if "machine_failure" in df.columns:
        modes = [c for c in df.columns if c.startswith("failure_")]
        payload["failure_balance"] = {
            "overall": {
                "positives": int(df["machine_failure"].sum()),
                "rows": int(len(df)),
                "rate": round(float(df["machine_failure"].mean()), 5),
            },
            "modes": [
                {
                    "column": c,
                    "label": c.replace("failure_", "").upper(),
                    "count": int(df[c].sum()),
                    "rate": round(float(df[c].mean()), 5),
                }
                for c in modes
            ],
        }
    payload["notes"] = list(schema.notes)
    return EDAResult(payload=payload)
