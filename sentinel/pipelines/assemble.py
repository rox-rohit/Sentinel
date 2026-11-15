"""Assemble fleet-level state from trained model outputs.

Everything here is derived: RUL comes from out-of-fold predictions, risk from
the empirical residual CDF, anomaly from the ensemble, and health from the
transparent scoring engine. No value in the fleet payload is random.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sentinel.config import HealthWeights, settings
from sentinel.decision.health import compute_health
from sentinel.models.rul import residual_cdf

INFORMATIVE_SENSORS = ["s2", "s3", "s4", "s7", "s8", "s9", "s11", "s12", "s13",
                       "s14", "s15", "s17", "s20", "s21"]
SERIES_SENSORS = ["s2", "s3", "s4", "s11"]
SENSOR_LABELS = {
    "s2": "Fan inlet pressure (P2)",
    "s3": "LPC outlet temperature (T24)",
    "s4": "LPC outlet pressure (P24)",
    "s7": "HPC outlet pressure (Ps30)",
    "s8": "Fuel flow ratio (phi)",
    "s9": "Corrected fan speed (NRf)",
    "s11": "HPC outlet pressure (Ps30)",
    "s12": "LPT outlet temperature (T50)",
    "s13": "Corrected fan speed (NRf)",
    "s14": "Corrected core speed (NRc)",
    "s15": "Bypass ratio (BPR)",
    "s17": "Bleed enthalpy (htBleed)",
    "s20": "HPT coolant bleed (W31)",
    "s21": "LPT coolant bleed (W32)",
}


def _downsample(values: np.ndarray, points: int) -> list:
    values = np.asarray(values)
    if len(values) == 0:
        return []
    if len(values) <= points:
        return [round(float(v), 4) for v in values]
    idx = np.linspace(0, len(values) - 1, points).round().astype(int)
    return [round(float(values[i]), 4) for i in idx]


def _trend_slope(series: np.ndarray, window: int = 10) -> float:
    values = np.asarray(series[-window:], dtype=float)
    if len(values) < 3:
        return 0.0
    x = np.arange(len(values))
    return float(np.polyfit(x, values, 1)[0])


def assemble_assets(
    *,
    feature_frame: pd.DataFrame,
    rul_predictions: pd.DataFrame,
    anomaly_frame: pd.DataFrame,
    residuals: np.ndarray,
    weights: HealthWeights | None = None,
    anomaly_reference: float = 1.0,
    anomaly_baseline: float = 0.0,
    points: int = 36,
) -> tuple[list[dict], pd.DataFrame]:
    """Return (asset payloads, enriched per-row frame)."""
    weights = (weights or settings.health_weights).normalized()
    sensor_cols = [c for c in INFORMATIVE_SENSORS if c in feature_frame.columns]
    base = feature_frame[["asset_id", "cycle", "rul", *sensor_cols]].merge(
        rul_predictions[["asset_id", "cycle", "predicted_rul", "lower", "upper"]],
        on=["asset_id", "cycle"], how="left", suffixes=("", "_truth"),
    ).merge(
        anomaly_frame[["asset_id", "cycle", "score", "severity", "isolation_forest", "lof",
                       "pca_reconstruction"]],
        on=["asset_id", "cycle"], how="left",
    )
    sorted_residuals = residual_cdf(residuals)

    scored = base["predicted_rul"].notna().to_numpy()
    risk_columns = {}
    for horizon in settings.horizon_cycles:
        query = float(horizon) - base["predicted_rul"].to_numpy(dtype=float)
        values = np.full(len(base), np.nan)
        values[scored] = (
            np.searchsorted(sorted_residuals, query[scored], side="right")
            / len(sorted_residuals)
        )
        risk_columns[f"risk_{horizon}"] = values
        base[f"risk_{horizon}"] = risk_columns[f"risk_{horizon}"]

    rul_health = np.clip(base["predicted_rul"], 0, settings.rul_clip) / settings.rul_clip * 100
    risk_health = (1.0 - base["risk_30"].clip(0, 1)) * 100
    anomaly_health = np.clip(
        100.0 - base["score"].fillna(0).clip(0, None) / max(0.05, anomaly_reference) * 100,
        0, 100,
    )
    base["base_health"] = (
        weights.rul * rul_health + weights.risk * risk_health + weights.anomaly * anomaly_health
    ) / (weights.rul + weights.risk + weights.anomaly)
    base.loc[~scored, "base_health"] = np.nan

    healthy_stats = {}
    healthy = base[base["cycle"] <= settings.healthy_cycle_limit + 30]
    for sensor in sensor_cols:
        healthy_stats[sensor] = (
            float(healthy[sensor].mean()),
            float(healthy[sensor].std() or 1.0),
        )

    assets: list[dict] = []
    for asset_id, group in base.groupby("asset_id", sort=True):
        group = group.sort_values("cycle")
        scored_group = group[group["predicted_rul"].notna()]
        latest = scored_group.iloc[-1] if len(scored_group) else group.iloc[-1]
        slope = _trend_slope(scored_group["base_health"].dropna().to_numpy())
        health = compute_health(
            predicted_rul=float(latest["predicted_rul"]),
            horizon_risk=float(latest["risk_30"]),
            anomaly_score=float(latest["score"] if pd.notna(latest["score"]) else 0.0),
            trend_slope=slope,
            weights=weights,
            anomaly_reference=anomaly_reference,
            anomaly_baseline=anomaly_baseline,
        )
        health_series = []
        for _, row in group.iterrows():
            if pd.isna(row["predicted_rul"]):
                health_series.append(None)
                continue
            health_series.append(compute_health(
                predicted_rul=float(row["predicted_rul"]),
                horizon_risk=float(row["risk_30"]),
                anomaly_score=float(row["score"] if pd.notna(row["score"]) else 0.0),
                trend_slope=slope,
                weights=weights,
                anomaly_reference=anomaly_reference,
                anomaly_baseline=anomaly_baseline,
            ).score)

        # Persist the per-cycle score so the replay artifact can stream it.
        base.loc[group.index, "health"] = [
            value if value is not None else np.nan for value in health_series
        ]

        z_scores = []
        for sensor in sensor_cols:
            mean, std = healthy_stats[sensor]
            z = (float(latest[sensor]) - mean) / std
            z_scores.append((sensor, z))
        z_scores.sort(key=lambda item: abs(item[1]), reverse=True)

        asset = {
            "id": f"FD001-{int(asset_id):03d}",
            "asset_id": int(asset_id),
            "label": f"Unit {int(asset_id):03d}",
            "dataset": "cmapss",
            "criticality": settings.criticality_default,
            "cycle": int(latest["cycle"]),
            "lifetime": int(group["cycle"].max()),
            "status": health.category,
            "health_score": health.score,
            "health_components": health.components,
            "health_explanation": health.explanation,
            "rul": {
                "estimate": round(float(latest["predicted_rul"]), 1),
                "lower": round(float(latest["lower"]), 1),
                "upper": round(float(latest["upper"]), 1),
                "clip": settings.rul_clip,
                "horizon_risk": {
                    str(h): round(float(latest[f"risk_{h}"]), 4) for h in settings.horizon_cycles
                },
            },
            "anomaly": {
                "score": round(float(latest["score"] if pd.notna(latest["score"]) else 0.0), 3),
                "severity": str(latest["severity"] if pd.notna(latest["severity"]) else "normal"),
                "detectors": {
                    "isolation_forest": round(float(latest["isolation_forest"]), 3)
                    if pd.notna(latest["isolation_forest"]) else 0.0,
                    "lof": round(float(latest["lof"]), 3) if pd.notna(latest["lof"]) else 0.0,
                    "pca_reconstruction": round(float(latest["pca_reconstruction"]), 3)
                    if pd.notna(latest["pca_reconstruction"]) else 0.0,
                },
                "top_sensors": [
                    {"sensor": sensor, "label": SENSOR_LABELS.get(sensor, sensor),
                     "z_score": round(z, 2), "value": round(float(latest[sensor]), 3)}
                    for sensor, z in z_scores[:4]
                ],
            },
            "degradation": {
                "health_slope_per_cycle": round(slope, 4),
                "direction": "deteriorating" if slope < -0.05 else "stable",
            },
            "latest_sensors": [
                {"sensor": sensor, "label": SENSOR_LABELS.get(sensor, sensor),
                 "value": round(float(latest[sensor]), 3),
                 "healthy_mean": round(healthy_stats[sensor][0], 3)}
                for sensor in sensor_cols
            ],
            "actual_rul_final": (
                round(float(latest["rul"]), 1) if "rul" in latest and pd.notna(latest["rul"]) else None
            ),
            "series": {
                "cycle": _downsample(group["cycle"].to_numpy(), points),
                "predicted_rul": _downsample(group["predicted_rul"].to_numpy(), points),
                "health": _downsample(np.array(health_series, dtype=float), points),
                "anomaly": _downsample(group["score"].fillna(0).to_numpy(), points),
                "sensors": {
                    sensor: _downsample(group[sensor].to_numpy(), points) for sensor in SERIES_SENSORS
                },
            },
            "source": "C-MAPSS FD001 held-out test trajectory (unit still in service)",
        }
        assets.append(asset)

    return assets, base


def build_alerts(assets: list[dict], *, limit: int = 60) -> list[dict]:
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "normal": 4}
    alerts = []
    for asset in assets:
        risk30 = asset["rul"]["horizon_risk"].get("30", 0.0)
        severity = asset["anomaly"]["severity"]
        if severity in {"high", "critical"}:
            top = asset["anomaly"]["top_sensors"][0] if asset["anomaly"]["top_sensors"] else None
            alerts.append({
                "asset_id": asset["id"],
                "label": asset["label"],
                "kind": "anomaly",
                "severity": "critical" if severity == "critical" else "high",
                "cycle": asset["cycle"],
                "score": asset["anomaly"]["score"],
                "message": (
                    f"Anomaly ensemble score {asset['anomaly']['score']:.2f}"
                    + (f"; largest deviation on {top['label']} ({top['z_score']:+.1f} sigma)." if top else ".")
                ),
                "sensors": [s["label"] for s in asset["anomaly"]["top_sensors"][:2]],
            })
        if risk30 >= 0.5 or asset["rul"]["estimate"] <= 15:
            alerts.append({
                "asset_id": asset["id"],
                "label": asset["label"],
                "kind": "failure_risk",
                "severity": "critical" if risk30 >= 0.8 else "high",
                "cycle": asset["cycle"],
                "score": risk30,
                "message": (
                    f"{risk30:.0%} estimated probability of reaching end of life within 30 cycles "
                    f"(predicted RUL {asset['rul']['estimate']:.0f} cycles)."
                ),
                "sensors": [s["label"] for s in asset["anomaly"]["top_sensors"][:2]],
            })
        elif asset["status"] in {"warning", "critical"}:
            alerts.append({
                "asset_id": asset["id"],
                "label": asset["label"],
                "kind": "health",
                "severity": "medium" if asset["status"] == "warning" else "high",
                "cycle": asset["cycle"],
                "score": asset["health_score"],
                "message": asset["health_explanation"],
                "sensors": [],
            })
    alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 9), -float(a["score"])))
    return alerts[:limit]
