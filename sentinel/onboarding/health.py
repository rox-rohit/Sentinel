"""Per-asset baseline health for partially mapped plant telemetry.

The 21-sensor RUL model is a C-MAPSS contract. A real export usually has fewer
channels, so onboarding learns a baseline from each asset's own early cycles and
scores departures from it with robust statistics, without inventing missing
sensors or borrowing a fleet baseline.

Signal requirements (reported explicitly by the API):

* 1 sensor + 10 cycles        -> a signal is produced, confidence low
* 3 sensors + 20 cycles       -> recommended minimum for a usable signal
* 6+ sensors                  -> high confidence
* 21 sensors + 30 cycles      -> full RUL model, still an opt-in
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from sentinel.decision.health import categorize

MIN_CYCLES_FOR_HEALTH = 10
RECOMMENDED_CYCLES = 20
MIN_SENSORS_FOR_SIGNAL = 1
RECOMMENDED_SENSORS = 3
HIGH_CONFIDENCE_SENSORS = 6
MAX_BASELINE_CYCLES = 30

SEVERITY_BANDS = (
    ("critical", 7.0),
    ("high", 5.0),
    ("medium", 3.5),
    ("low", 2.5),
    ("normal", 0.0),
)


def _mad(values: np.ndarray) -> float:
    median = float(np.median(values))
    return float(np.median(np.abs(values - median))) * 1.4826


def _slope(cycles: np.ndarray, values: np.ndarray) -> float:
    if len(cycles) < 2:
        return 0.0
    return float(np.polyfit(cycles.astype(float), values.astype(float), 1)[0])


def _severity(score: float) -> str:
    for label, floor in SEVERITY_BANDS:
        if score >= floor:
            return label
    return "normal"


def build_baseline(frame: pd.DataFrame, sensors: list[str]) -> dict | None:
    """Learn median, noise and natural slope from an asset's first cycles."""
    usable = [sensor for sensor in sensors if sensor in frame.columns]
    frame = frame.dropna(subset=["cycle"]).sort_values("cycle")
    if len(frame) < MIN_CYCLES_FOR_HEALTH or not usable:
        return None
    window = min(MAX_BASELINE_CYCLES, max(MIN_CYCLES_FOR_HEALTH, math.ceil(len(frame) * 0.3)))
    window = min(window, len(frame))
    early = frame.head(window)
    baseline = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_cycles": int(window),
        "baseline_from": int(early["cycle"].min()),
        "baseline_to": int(early["cycle"].max()),
        "baseline_mid_cycle": float(early["cycle"].mean()),
        "sensors": {},
    }
    for sensor in usable:
        values = early[sensor].dropna().to_numpy(dtype=float)
        if len(values) < 3:
            continue
        median = float(np.median(values))
        noise = _mad(values)
        if noise <= 0:
            noise = max(abs(median) * 0.01, 1e-6)
        baseline["sensors"][sensor] = {
            "median": round(median, 6),
            "mad": round(noise, 6),
            "slope": round(_slope(early["cycle"].to_numpy(dtype=float),
                                  early[sensor].to_numpy(dtype=float)), 8),
            "count": len(values),
        }
    if not baseline["sensors"]:
        return None
    return baseline


def baseline_is_usable(baseline: dict | None) -> bool:
    return bool(baseline and baseline.get("sensors"))


def assess(frame: pd.DataFrame, baseline: dict) -> dict:
    """Score the latest cycle against the asset's own baseline."""
    frame = frame.dropna(subset=["cycle"]).sort_values("cycle")
    if frame.empty:
        raise ValueError("No rows to assess.")
    latest = frame.iloc[-1]
    cycle = float(latest["cycle"])
    sensors = baseline.get("sensors", {})
    mid = float(baseline.get("baseline_mid_cycle", 0.0))
    recent = frame.tail(min(len(frame), max(5, int(len(frame) * 0.2))))

    evaluations = []
    for sensor, stats in sensors.items():
        if sensor not in frame.columns:
            continue
        value = latest.get(sensor)
        if pd.isna(value):
            continue
        expected = float(stats["median"]) + float(stats["slope"]) * (cycle - mid)
        noise = max(float(stats["mad"]), 1e-6)
        z = (float(value) - expected) / noise
        recent_values = recent[sensor].dropna()
        recent_slope = (_slope(recent.loc[recent_values.index, "cycle"].to_numpy(dtype=float),
                               recent_values.to_numpy(dtype=float))
                        if len(recent_values) >= 2 else 0.0)
        trend_excess = recent_slope - float(stats["slope"])
        trend_noise = noise / max(1.0, math.sqrt(max(1, len(recent_values))))
        trend_z = trend_excess / max(trend_noise, 1e-6)
        evaluations.append({
            "sensor": sensor,
            "value": round(float(value), 4),
            "baseline_median": round(float(stats["median"]), 4),
            "expected": round(expected, 4),
            "z_score": round(z, 3),
            "deviation": round(float(value) - float(stats["median"]), 4),
            "recent_slope": round(recent_slope, 8),
            "trend_z": round(trend_z, 3),
        })

    if not evaluations:
        raise ValueError("No mapped sensor has a value at the latest cycle.")

    z_values = sorted((abs(item["z_score"]) for item in evaluations), reverse=True)
    anomaly_score = float(np.mean(z_values[:min(3, len(z_values))]))
    severity = _severity(anomaly_score)

    worsening = [max(0.0, item["trend_z"]) for item in evaluations]
    trend_score = float(np.mean(sorted(worsening, reverse=True)[:min(2, len(worsening))]))

    # A 2-sigma band is treated as normal run-to-run variation; only excess
    # departure consumes health, so a stable asset stays in the healthy band.
    anomaly_penalty = min(70.0, max(0.0, anomaly_score - 2.0) * 14.0)
    trend_penalty = min(30.0, max(0.0, trend_score - 1.0) * 6.0)
    health_score = round(max(0.0, 100.0 - anomaly_penalty - trend_penalty), 1)
    category = categorize(health_score)

    sensor_count = len(evaluations)
    baseline_cycles = int(baseline.get("baseline_cycles", 0))
    if sensor_count >= HIGH_CONFIDENCE_SENSORS and baseline_cycles >= RECOMMENDED_CYCLES:
        confidence = "high"
    elif sensor_count >= RECOMMENDED_SENSORS and baseline_cycles >= MIN_CYCLES_FOR_HEALTH:
        confidence = "medium"
    else:
        confidence = "low"

    evaluations.sort(key=lambda item: abs(item["z_score"]), reverse=True)
    top = evaluations[0]
    explanation = (
        f"Health {health_score:.1f}/100 ({category}) from {sensor_count} mapped sensor(s) "
        f"against a {baseline_cycles}-cycle baseline. Largest departure: {top['sensor']} "
        f"at {top['z_score']:+.1f} robust sigma ({confidence} confidence)."
    )
    return {
        "usable": True,
        "health_score": health_score,
        "category": category,
        "anomaly_score": round(anomaly_score, 3),
        "severity": severity,
        "trend_score": round(trend_score, 3),
        "components": {
            "anomaly_penalty": round(anomaly_penalty, 1),
            "trend_penalty": round(trend_penalty, 1),
        },
        "sensors": evaluations,
        "top_sensor": top["sensor"],
        "coverage": {
            "sensors": sensor_count,
            "baseline_cycles": baseline_cycles,
            "confidence": confidence,
            "min_sensors_for_signal": MIN_SENSORS_FOR_SIGNAL,
            "recommended_sensors": RECOMMENDED_SENSORS,
            "high_confidence_sensors": HIGH_CONFIDENCE_SENSORS,
        },
        "cycle": int(cycle),
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "explanation": explanation,
        "limitations": [
            "Baseline learned from this asset's early cycles, not a fleet reference.",
            "Health is relative to the baseline window; a baseline taken during a fault will hide it.",
            f"{sensor_count} sensor(s) mapped — fewer channels give a weaker signal.",
            "Partial-sensor health does not estimate remaining useful life; the 21-sensor "
            "RUL score remains a separate opt-in.",
        ],
    }


def insufficient_signal(frame: pd.DataFrame, sensors: list[str], mapped_sensors: int) -> dict:
    usable = [sensor for sensor in sensors if sensor in frame.columns]
    cycles = int(frame["cycle"].dropna().shape[0]) if "cycle" in frame.columns else 0
    reasons = []
    if not usable or len(usable) < MIN_SENSORS_FOR_SIGNAL:
        reasons.append("No mapped sensor is present.")
    if cycles < MIN_CYCLES_FOR_HEALTH:
        reasons.append(
            f"{cycles} cycles recorded; at least {MIN_CYCLES_FOR_HEALTH} are needed for a baseline."
        )
    return {
        "usable": False,
        "reasons": reasons,
        "coverage": {
            "sensors": mapped_sensors,
            "baseline_cycles": 0,
            "confidence": "none",
            "min_sensors_for_signal": MIN_SENSORS_FOR_SIGNAL,
            "recommended_sensors": RECOMMENDED_SENSORS,
            "high_confidence_sensors": HIGH_CONFIDENCE_SENSORS,
        },
    }


def health_thresholds() -> dict:
    return {
        "min_cycles": MIN_CYCLES_FOR_HEALTH,
        "recommended_cycles": RECOMMENDED_CYCLES,
        "min_sensors": MIN_SENSORS_FOR_SIGNAL,
        "recommended_sensors": RECOMMENDED_SENSORS,
        "high_confidence_sensors": HIGH_CONFIDENCE_SENSORS,
        "baseline_max_cycles": MAX_BASELINE_CYCLES,
        "severity_bands": {label: floor for label, floor in SEVERITY_BANDS},
        "health_bands": {"healthy": 80.0, "attention": 60.0, "warning": 40.0, "critical": 0.0},
    }
