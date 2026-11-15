"""Transparent machine health scoring.

The score is a weighted combination of four signals, each mapped to a 0-100
health contribution and returned alongside the total so a user can see exactly
why an asset scored what it scored. It is a decision aid with published
weights, not a validated physical measurement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sentinel.config import HealthWeights, settings

CATEGORY_BANDS = (
    ("healthy", 80.0),
    ("attention", 60.0),
    ("warning", 40.0),
    ("critical", 0.0),
)


@dataclass
class HealthResult:
    score: float
    category: str
    components: dict
    explanation: str


def categorize(score: float) -> str:
    for label, floor in CATEGORY_BANDS:
        if score >= floor:
            return label
    return "critical"


def compute_health(
    *,
    predicted_rul: float,
    horizon_risk: float,
    anomaly_score: float,
    trend_slope: float,
    weights: HealthWeights | None = None,
    rul_clip: int | None = None,
    anomaly_reference: float = 1.0,
    anomaly_baseline: float = 0.0,
) -> HealthResult:
    """Combine RUL headroom, horizon risk, anomaly level and degradation trend."""
    weights = (weights or settings.health_weights).normalized()
    rul_clip = rul_clip or settings.rul_clip

    rul_health = float(min(100.0, max(0.0, predicted_rul) / rul_clip * 100.0))
    risk_health = float((1.0 - min(1.0, max(0.0, horizon_risk))) * 100.0)
    # Anomaly health is anchored to the healthy median score and the calibrated
    # high-severity threshold, so "normal" readings stay healthy and only real
    # departures consume the component.
    reference = max(0.05, float(anomaly_reference))
    baseline = float(anomaly_baseline)
    span = max(0.05, reference - baseline)
    ratio = min(1.0, max(0.0, (float(anomaly_score) - baseline) / span))
    anomaly_health = float((1.0 - ratio) * 100.0)
    # Positive slope means the health trend is falling; normalise against 1 point/cycle.
    trend_health = float(max(0.0, 100.0 - min(100.0, abs(min(0.0, -trend_slope)) * 100.0)))

    components = {
        "rul_health": round(rul_health, 1),
        "risk_health": round(risk_health, 1),
        "anomaly_health": round(anomaly_health, 1),
        "trend_health": round(trend_health, 1),
    }
    score = (
        weights.rul * rul_health
        + weights.risk * risk_health
        + weights.anomaly * anomaly_health
        + weights.trend * trend_health
    )
    score = round(min(100.0, max(0.0, score)), 1)
    category = categorize(score)

    weakest = min(components.items(), key=lambda item: item[1])
    labels = {
        "rul_health": "remaining useful life",
        "risk_health": "horizon failure risk",
        "anomaly_health": "anomaly departure from healthy behaviour",
        "trend_health": "sensor degradation trend",
    }
    explanation = (
        f"Health {score:.1f}/100 ({category}). Weakest signal: {labels[weakest[0]]} "
        f"({weakest[1]:.0f}/100). Weights: RUL {weights.rul:.2f}, risk {weights.risk:.2f}, "
        f"anomaly {weights.anomaly:.2f}, trend {weights.trend:.2f}."
    )
    return HealthResult(score=score, category=category, components=components,
                        explanation=explanation)


def weights_payload() -> dict:
    w = settings.health_weights.normalized()
    return {
        "weights": asdict(w),
        "method": "weighted sum of four 0-100 sub-scores, documented and configurable",
        "bands": {label: floor for label, floor in CATEGORY_BANDS},
        "limitations": [
            "Not a validated physical health index; weights are engineering judgement.",
            "RUL and anomaly components are dataset-specific models.",
        ],
    }
