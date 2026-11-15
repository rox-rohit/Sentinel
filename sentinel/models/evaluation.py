"""Task-appropriate metrics.

Classification is evaluated with recall/precision/F1/ROC-AUC/PR-AUC and an
explicit expected-cost objective — never accuracy alone. Regression uses
MAE/RMSE plus the NASA asymmetric score that penalises late RUL predictions.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    root_mean_squared_error,
)


def classification_metrics(y_true, y_prob, threshold: float = 0.5) -> dict:
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    y_pred = (y_prob >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    metrics = {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else None,
        "pr_auc": float(average_precision_score(y_true, y_prob)) if y_true.sum() else None,
        "true_positive": int(tp),
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else 0.0,
        "false_negative_rate": float(fn / (fn + tp)) if (fn + tp) else 0.0,
        "support": int(len(y_true)),
        "positives": int(y_true.sum()),
    }
    metrics["confusion_matrix"] = [[int(tn), int(fp)], [int(fn), int(tp)]]
    return metrics


def expected_cost(y_true, y_prob, threshold: float, *, fn_cost: float, fp_cost: float) -> float:
    y_true = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    return float(fn * fn_cost + fp * fp_cost)


def threshold_curve(y_true, y_prob, *, fn_cost: float, fp_cost: float) -> dict:
    """Sweep thresholds and return the cost-minimising one plus the sweep."""
    thresholds = np.round(np.linspace(0.02, 0.98, 97), 4)
    rows = []
    for t in thresholds:
        m = classification_metrics(y_true, y_prob, float(t))
        rows.append({
            "threshold": float(t),
            "recall": m["recall"],
            "precision": m["precision"],
            "f1": m["f1"],
            "expected_cost": expected_cost(y_true, y_prob, float(t), fn_cost=fn_cost, fp_cost=fp_cost),
        })
    best = min(rows, key=lambda r: (r["expected_cost"], -r["recall"]))
    return {"best": best, "curve": rows}


def nasa_score(y_true, y_pred) -> float:
    """NASA C-MAPSS asymmetric scoring function.

    Early predictions (d = y_pred - y_true < 0) are rewarded; late predictions
    are penalised much more heavily (exp(d/10) vs exp(-d/13)).
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    d = y_pred - y_true
    return float(np.sum(np.where(d < 0, np.exp(-d / 13.0) - 1.0, np.exp(d / 10.0) - 1.0)))


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    errors = y_pred - y_true
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "nasa_score": nasa_score(y_true, y_pred),
        "bias": float(np.mean(errors)),
        "p90_abs_error": float(np.percentile(np.abs(errors), 90)),
        "support": int(len(y_true)),
    }


def psi(expected, actual, bins: int = 10) -> float:
    """Population Stability Index between a reference and current sample."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    if len(expected) < 20 or len(actual) < 20:
        return 0.0
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    exp_pct = np.histogram(expected, bins=edges)[0] / len(expected)
    act_pct = np.histogram(actual, bins=edges)[0] / len(actual)
    exp_pct = np.clip(exp_pct, 1e-4, None)
    act_pct = np.clip(act_pct, 1e-4, None)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def psi_status(value: float) -> str:
    if value < 0.1:
        return "stable"
    if value < 0.25:
        return "monitor"
    return "drift"
