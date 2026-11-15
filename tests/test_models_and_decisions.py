"""Metric, decision-engine and RUL-risk tests."""

from __future__ import annotations

import itertools

import numpy as np

from sentinel.decision.health import categorize, compute_health
from sentinel.decision.optimizer import build_plan
from sentinel.models.classification import classifier_candidates
from sentinel.models.evaluation import (
    classification_metrics,
    expected_cost,
    nasa_score,
    psi,
    psi_status,
    regression_metrics,
    threshold_curve,
)


def test_classification_metrics_use_probabilities_not_accuracy():
    y = np.array([1] * 5 + [0] * 95)
    perfect = np.array([0.9] * 5 + [0.05] * 95)
    lazy = np.array([0.01] * 100)  # predicts all-negative: 95% accuracy, zero recall
    good = classification_metrics(y, perfect, 0.5)
    bad = classification_metrics(y, lazy, 0.5)
    assert good["recall"] == 1.0 and good["pr_auc"] == 1.0
    assert bad["recall"] == 0.0
    assert bad["false_negative"] == 5
    assert bad["support"] == len(y)


def test_threshold_optimisation_reacts_to_asymmetric_costs():
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0])
    prob = np.array([0.4, 0.35, 0.3, 0.45, 0.2, 0.1, 0.05, 0.02])
    expensive_miss = threshold_curve(y, prob, fn_cost=10_000, fp_cost=10)
    cheap_miss = threshold_curve(y, prob, fn_cost=10, fp_cost=10_000)
    assert expensive_miss["best"]["threshold"] <= cheap_miss["best"]["threshold"]
    assert expected_cost(y, prob, 0.9, fn_cost=1000, fp_cost=1) > 0


def test_nasa_score_penalises_late_predictions_more():
    truth = np.array([50.0])
    early = nasa_score(truth, np.array([40.0]))
    late = nasa_score(truth, np.array([60.0]))
    assert early < late
    assert nasa_score(truth, truth) == 0.0


def test_regression_metrics_and_psi_status():
    metrics = regression_metrics([10, 20, 30], [12, 19, 33])
    assert metrics["support"] == 3
    assert metrics["mae"] == 2.0
    assert metrics["bias"] > 0
    stable = psi(np.linspace(0, 1, 500), np.linspace(0, 1, 500))
    shifted = psi(np.linspace(0, 1, 500), np.linspace(2, 3, 500))
    assert stable < 0.05
    assert shifted > 0.25
    assert psi_status(shifted) == "drift"


def test_classifier_registry_exposes_expected_algorithms():
    candidates = classifier_candidates(seed=1, scale_pos_weight=10)
    assert {"LogisticRegression", "RandomForest", "ExtraTrees",
            "HistGradientBoosting", "XGBoost"}.issubset(candidates)


def test_health_score_is_monotonic_and_categorised():
    healthy = compute_health(predicted_rul=120, horizon_risk=0.02, anomaly_score=0.1, trend_slope=0)
    degrading = compute_health(predicted_rul=40, horizon_risk=0.6, anomaly_score=1.2, trend_slope=-0.8)
    failing = compute_health(predicted_rul=3, horizon_risk=0.99, anomaly_score=3.0, trend_slope=-2.0)
    assert healthy.score > degrading.score > failing.score
    assert healthy.category == "healthy"
    assert failing.category == "critical"
    assert set(healthy.components) == {"rul_health", "risk_health", "anomaly_health", "trend_health"}
    assert categorize(65) == "attention"
    assert categorize(41) == "warning"


def test_knapsack_matches_brute_force_and_respects_budget():
    assets = [
        {"asset_id": "A", "failure_risk": 0.9, "predicted_rul": 12, "criticality": 3},
        {"asset_id": "B", "failure_risk": 0.6, "predicted_rul": 40, "criticality": 2},
        {"asset_id": "C", "failure_risk": 0.3, "predicted_rul": 80, "criticality": 1},
        {"asset_id": "D", "failure_risk": 0.8, "predicted_rul": 20, "criticality": 2},
    ]
    plan = build_plan(assets, budget=300)
    spent = sum(row["planned_cost"] for row in plan.selected)
    assert spent <= 300
    assert plan.selected, "at least one action should fit the budget"

    # Exhaustive check on the same cost model: no feasible subset beats it.
    costs = 120.0
    best_benefit = 0.0
    for size in range(1, len(assets) + 1):
        for subset in itertools.combinations(assets, size):
            if size * costs > 300:
                continue
            benefit = sum(
                asset["failure_risk"] * 500.0 - costs for asset in subset
            )
            best_benefit = max(best_benefit, benefit)
    chosen_benefit = sum(
        row["failure_risk"] * 500.0 - row["planned_cost"] for row in plan.selected
    )
    assert chosen_benefit == round(best_benefit, 2)
    assert [s["strategy"] for s in plan.scenarios] == ["reactive", "preventive", "predictive"]
    assert plan.assumptions["false_negative_cost"] > 0
