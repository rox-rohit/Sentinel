"""Snapshot composition — the single payload the UI reads.

Sections map to pages: fleet, assets, predictive, anomalies, rul, explainability,
maintenance, models, datasets, eda, drift, settings, system.
"""

from __future__ import annotations

import math

import numpy as np

from sentinel.config import settings
from sentinel.decision.health import weights_payload


def sanitize(value):
    """Replace non-finite numbers with null so the payload is valid JSON.

    NaN/Infinity appear legitimately (skew of a constant channel, an empty PSI
    bin). JSON has no representation for them, and the browser would reject the
    file, so they become null and the UI renders them as a dash.
    """
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _risk_distribution(assets: list[dict]) -> list[dict]:
    buckets = [(0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]
    labels = ["0-10%", "10-25%", "25-50%", "50-75%", "75-100%"]
    counts = [0] * len(buckets)
    for asset in assets:
        risk = asset["rul"]["horizon_risk"].get("30", 0.0)
        for index, (low, high) in enumerate(buckets):
            if low <= risk < high:
                counts[index] += 1
                break
    return [{"band": label, "count": count} for label, count in zip(labels, counts)]


def _anomaly_histogram(frame, bins: int = 24) -> dict:
    scores = frame["score"].dropna().to_numpy()
    if len(scores) == 0:
        return {"counts": [], "edges": []}
    counts, edges = np.histogram(np.clip(scores, 0, 5), bins=bins, range=(0, 5))
    return {"counts": [int(c) for c in counts], "edges": [round(float(e), 2) for e in edges]}


def compose_snapshot(*, meta, assets, alerts, rul_result, classifier_result, anomaly_result,
                     maintenance, explainability, drift, models, datasets, eda,
                     forecast) -> dict:
    summary = {
        "total": len(assets),
        "healthy": sum(1 for a in assets if a["status"] == "healthy"),
        "attention": sum(1 for a in assets if a["status"] == "attention"),
        "warning": sum(1 for a in assets if a["status"] == "warning"),
        "critical": sum(1 for a in assets if a["status"] == "critical"),
        "avg_health": round(float(np.mean([a["health_score"] for a in assets])), 1),
        "avg_rul": round(float(np.mean([a["rul"]["estimate"] for a in assets])), 1),
        "active_anomalies": sum(
            1 for a in assets if a["anomaly"]["severity"] in {"high", "critical"}
        ),
        "predicted_failures_30": sum(
            1 for a in assets if a["rul"]["horizon_risk"].get("30", 0) >= 0.5
        ),
        "predicted_failures_10": sum(
            1 for a in assets if a["rul"]["horizon_risk"].get("10", 0) >= 0.5
        ),
        "maintenance_actions": len(maintenance["selected"]),
        "budget": maintenance["budget"],
        "planned_spend": maintenance["spent"],
        "deferred": len(maintenance["deferred"]),
        "alerts": len(alerts),
    }

    fleet = {
        "summary": summary,
        "health_distribution": [
            {"category": category, "count": sum(1 for a in assets if a["status"] == category)}
            for category in ("healthy", "attention", "warning", "critical")
        ],
        "risk_distribution": _risk_distribution(assets),
        "health_weights": weights_payload(),
        "data_source": "C-MAPSS FD001 · held-out test trajectories (out-of-sample RUL)",
    }

    predictive = {
        "risk_distribution": fleet["risk_distribution"],
        "horizon_curve": [
            {
                "horizon": horizon,
                "high_risk": sum(1 for a in assets if a["rul"]["horizon_risk"].get(str(horizon), 0) >= 0.5),
                "mean_risk": round(float(np.mean([
                    a["rul"]["horizon_risk"].get(str(horizon), 0) for a in assets
                ])), 4),
            }
            for horizon in settings.horizon_cycles
        ],
        "highest_risk": sorted(
            [
                {
                    "id": a["id"], "label": a["label"], "health": a["health_score"],
                    "risk_10": a["rul"]["horizon_risk"].get("10", 0),
                    "risk_30": a["rul"]["horizon_risk"].get("30", 0),
                    "risk_50": a["rul"]["horizon_risk"].get("50", 0),
                    "rul": a["rul"]["estimate"], "lower": a["rul"]["lower"],
                    "upper": a["rul"]["upper"], "status": a["status"],
                }
                for a in assets
            ],
            key=lambda row: row["risk_30"],
            reverse=True,
        )[:12],
        "confidence": {
            "mean_interval_width": round(float(np.mean([
                a["rul"]["upper"] - a["rul"]["lower"] for a in assets
            ])), 1),
            "residual_quantiles": rul_result.residual_quantiles,
        },
        "model": rul_result.best_name,
        "method": "P(RUL <= horizon) from the empirical residual CDF of the RUL model",
    }

    severity_counts = {key: 0 for key in ("normal", "low", "medium", "high", "critical")}
    sensor_hits: dict[str, int] = {}
    for asset in assets:
        severity = asset["anomaly"]["severity"]
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        for sensor in asset["anomaly"]["top_sensors"]:
            sensor_hits[sensor["label"]] = sensor_hits.get(sensor["label"], 0) + 1
    anomaly_center = {
        "summary": anomaly_result.summary,
        "severity_distribution": severity_counts,
        "score_histogram": _anomaly_histogram(anomaly_result.frame),
        "recent": [a for a in alerts if a["kind"] == "anomaly"][:20],
        "affected_sensors": sorted(
            [{"sensor": key, "assets": value} for key, value in sensor_hits.items()],
            key=lambda row: row["assets"], reverse=True,
        )[:8],
        "scored_rows": int(len(anomaly_result.frame)),
    }

    rul_page = {
        "benchmark": {
            "official": rul_result.official_test_metrics,
            "validation": rul_result.validation_metrics,
            "comparison": rul_result.comparison,
            "residuals": rul_result.residual_quantiles,
            "clip": settings.rul_clip,
            "protocol": (
                "80/20 engine-wise split for model selection, refit on all training units, "
                "official test scored once at each unit's final cycle"
            ),
        },
        "points": rul_result.official_points,
        "fleet": [
            {"id": a["id"], "estimate": a["rul"]["estimate"], "lower": a["rul"]["lower"],
             "upper": a["rul"]["upper"], "status": a["status"]}
            for a in assets
        ],
        "warnings": rul_result.warnings,
        "limitations": [
            "RUL is expressed in operating cycles, not calendar time.",
            f"Training targets are clipped at {settings.rul_clip} cycles.",
            "The band is an empirical residual interval, not a calibrated guarantee.",
            "C-MAPSS is simulated; real assets need condition normalisation and maintenance history.",
        ],
    }

    return {
        "meta": meta,
        "fleet": fleet,
        "assets": assets,
        "alerts": alerts,
        "predictive": predictive,
        "anomalies": anomaly_center,
        "rul": rul_page,
        "explainability": explainability,
        "forecast": forecast,
        "maintenance": maintenance,
        "models": models,
        "datasets": datasets,
        "eda": eda,
        "drift": drift,
        "settings": {
            "costs": settings.costs.__dict__,
            "health": weights_payload(),
            "horizons": list(settings.horizon_cycles),
            "rul_clip": settings.rul_clip,
            "rolling_windows": list(settings.rolling_windows),
            "budget": settings.maintenance_budget,
            "failure_threshold": classifier_result.threshold,
            "cmapss_subset": settings.cmapss_subset,
        },
    }
