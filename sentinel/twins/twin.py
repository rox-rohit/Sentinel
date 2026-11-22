"""Baseline-relative digital-twin state estimation.

A twin is bound to a fleet asset. The first cycles of that asset's recorded
trajectory (the healthy part of the run) define a *baseline*: a median and a
robust scale (1.4826 x MAD) per sensor channel. Every ingested sample is then
compared with that baseline.

The health score is transparent arithmetic, not a model output:

    deviation_index   = 0.65 * max(|z|) + 0.35 * median(|z|)
    deviation_penalty = min(50, 11 * deviation_index)
    coverage_penalty  = 20 * (1 - matched / expected)
    health            = clamp(100 - deviation_penalty - coverage_penalty, 0, 100)

The peak term is what makes a single failing channel matter: a pure median
would ignore one spiking sensor on a small channel set. The median term keeps a
single noisy channel from dominating when the rest of the machine is healthy.

Coverage is part of the score on purpose: a twin fed by two of eight channels
must not report a confident 100. The function is deterministic and unit-tested;
the API never invents a value for a channel that was not sent.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Mapping

HEALTH_BANDS: dict[str, float] = {"healthy": 80.0, "attention": 60.0, "warning": 40.0}
SEVERITY_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("normal", 1.5),
    ("low", 2.5),
    ("medium", 3.5),
    ("high", 5.0),
)
MAX_TOP_SENSORS = 5
DEFAULT_BASELINE_CYCLES = 30


def finite(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None`` when it is not usable."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def classify_health(score: float) -> str:
    if score >= HEALTH_BANDS["healthy"]:
        return "healthy"
    if score >= HEALTH_BANDS["attention"]:
        return "attention"
    if score >= HEALTH_BANDS["warning"]:
        return "warning"
    return "critical"


def severity_for(z_score: float) -> str:
    magnitude = abs(z_score)
    for name, threshold in SEVERITY_THRESHOLDS:
        if magnitude < threshold:
            return name
    return "critical"


def build_baseline(
    sensor_series: Mapping[str, list[Any]],
    cycles: int = DEFAULT_BASELINE_CYCLES,
) -> dict:
    """Summarise the healthy head of a recorded trajectory.

    ``sensor_series`` maps channel -> chronological values. Only finite values
    in the first ``cycles`` positions are used, so a sparse channel still
    produces a baseline when it has at least three readings.
    """
    channels: dict[str, dict[str, float]] = {}
    for key, values in sensor_series.items():
        head = [number for number in (finite(v) for v in list(values)[:cycles]) if number is not None]
        if len(head) < 3:
            continue
        median = statistics.median(head)
        mad = statistics.median([abs(value - median) for value in head])
        scale = 1.4826 * mad
        if scale <= 0:
            spread = statistics.pstdev(head)
            scale = spread if spread > 0 else max(abs(median) * 0.01, 1e-6)
        channels[str(key)] = {
            "median": round(median, 6),
            "scale": round(scale, 6),
            "samples": len(head),
        }
    return {
        "cycles": cycles,
        "manual_cycles": sum(channel["samples"] for channel in channels.values()),
        "sensor_count": len(channels),
        "channels": channels,
    }


def assess(sensors: Mapping[str, Any], baseline: Mapping[str, Any] | None) -> dict:
    """Score one sample against the baseline.

    Unknown channels are reported, never silently folded into the score.
    """
    normalised: dict[str, float] = {}
    rejected: list[str] = []
    for key, raw in sensors.items():
        value = finite(raw)
        if value is None:
            rejected.append(str(key))
        else:
            normalised[str(key)] = value

    expected = (baseline or {}).get("channels", {}) or {}
    expected_keys = list(expected)

    readings: list[dict] = []
    z_scores: list[float] = []
    for key, channel in expected.items():
        if key not in normalised:
            continue
        value = normalised[key]
        scale = finite(channel.get("scale")) or 1e-6
        median = finite(channel.get("median")) or 0.0
        z = (value - median) / scale
        z_scores.append(z)
        readings.append({
            "sensor": key,
            "value": round(value, 4),
            "median": round(median, 4),
            "scale": round(scale, 4),
            "z_score": round(z, 3),
            "deviation_pct": round((value - median) / abs(median) * 100, 2) if median else None,
        })

    matched = len(readings)
    coverage = (matched / len(expected_keys)) if expected_keys else 0.0
    unknown = sorted(set(normalised) - set(expected_keys))
    missing = [key for key in expected_keys if key not in normalised]

    if matched == 0:
        return {
            "usable": False,
            "health_score": None,
            "category": None,
            "anomaly_score": None,
            "severity": None,
            "coverage": {
                "expected": len(expected_keys),
                "matched": 0,
                "coverage": 0.0,
                "missing": missing,
                "unknown": unknown,
                "rejected": rejected,
            },
            "sensors": [],
            "top_sensors": [],
            "explanation": (
                "No ingested channel matched the twin baseline. Send at least one of: "
                + ", ".join(expected_keys[:8])
            )
            if expected_keys
            else "This twin has no baseline; bind it to a fleet asset with recorded telemetry.",
        }

    peak_abs_z = max(abs(z) for z in z_scores)
    median_abs_z = statistics.median([abs(z) for z in z_scores])
    deviation_index = 0.65 * peak_abs_z + 0.35 * median_abs_z
    deviation_penalty = min(50.0, 11.0 * deviation_index)
    coverage_penalty = 20.0 * (1.0 - coverage)
    health = max(0.0, min(100.0, 100.0 - deviation_penalty - coverage_penalty))
    worst = max(z_scores, key=abs)
    severity = severity_for(deviation_index)

    readings.sort(key=lambda entry: abs(entry["z_score"]), reverse=True)
    top = readings[:MAX_TOP_SENSORS]
    summary = (
        f"{matched} of {len(expected_keys)} channels matched the baseline; "
        f"peak {worst:+.2f}σ, median {median_abs_z:.2f}σ, index {deviation_index:.2f}σ. "
        f"Health {health:.0f}/100 after {deviation_penalty:.0f} deviation and "
        f"{coverage_penalty:.0f} coverage penalty."
    )

    return {
        "usable": True,
        "health_score": round(health, 1),
        "category": classify_health(health),
        "anomaly_score": round(deviation_index, 3),
        "severity": severity,
        "coverage": {
            "expected": len(expected_keys),
            "matched": matched,
            "coverage": round(coverage, 3),
            "missing": missing,
            "unknown": unknown,
            "rejected": rejected,
        },
        "sensors": sorted(readings, key=lambda entry: entry["sensor"]),
        "top_sensors": top,
        "explanation": summary,
    }


def trend(samples: list[dict]) -> dict:
    """Health direction over the last ingested samples (no extrapolation)."""
    points = [entry for entry in samples if entry.get("health") is not None]
    if len(points) < 4:
        return {"direction": "unknown", "slope_per_sample": None, "window": len(points)}
    window = points[-24:]
    first = float(window[0]["health"])
    last = float(window[-1]["health"])
    slope = (last - first) / max(1, len(window) - 1)
    if slope < -0.4:
        direction = "degrading"
    elif slope > 0.4:
        direction = "recovering"
    else:
        direction = "stable"
    return {
        "direction": direction,
        "slope_per_sample": round(slope, 3),
        "window": len(window),
        "delta": round(last - first, 2),
    }
