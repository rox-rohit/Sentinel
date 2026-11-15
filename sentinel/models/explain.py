"""Explainability: exact TreeSHAP for XGBoost, model-agnostic occlusion otherwise.

Attribution describes what the model used, not physical causation. The API and
UI repeat that distinction wherever these values appear.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb


def is_xgboost(model) -> bool:
    return hasattr(model, "get_booster")


def xgb_shap_matrix(model, X: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Exact additive feature attributions from XGBoost's TreeSHAP.

    Returns (values[n_samples, n_features], expected_value).
    """
    booster = model.get_booster()
    dmatrix = xgb.DMatrix(X, feature_names=list(X.columns))
    contribs = booster.predict(dmatrix, pred_contribs=True)
    contribs = np.asarray(contribs)
    if contribs.ndim == 1:
        contribs = contribs.reshape(1, -1)
    return contribs[:, :-1], float(contribs[:, -1].mean())


def global_shap_importance(model, X: pd.DataFrame, top_k: int = 12) -> list[dict]:
    values, _ = xgb_shap_matrix(model, X)
    mean_abs = np.abs(values).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][:top_k]
    return [
        {
            "feature": X.columns[i],
            "mean_abs_shap": float(mean_abs[i]),
            "mean_signed_shap": float(values[:, i].mean()),
            "method": "TreeSHAP (XGBoost pred_contribs)",
        }
        for i in order
    ]


@dataclass
class LocalExplanation:
    probability: float
    baseline_probability: float
    contributions: list[dict]
    method: str


def occlusion_explanation(
    predict_proba,
    row: pd.Series,
    reference: pd.Series,
    *,
    top_k: int = 8,
    method_label: str = "occlusion (feature replaced by training median)",
) -> LocalExplanation:
    """Model-agnostic local attribution.

    Each feature is replaced by a reference (median) value and the change in the
    predicted probability is measured. Positive contributions pushed the
    prediction up relative to the reference point.
    """
    features = [c for c in row.index if c in reference.index]
    base_input = pd.DataFrame([row[features].to_numpy(dtype=float)], columns=features)
    base_prob = float(np.asarray(predict_proba(base_input))[0, 1])
    contributions = []
    for feature in features:
        perturbed = base_input.copy()
        perturbed.loc[0, feature] = float(reference[feature])
        delta = base_prob - float(np.asarray(predict_proba(perturbed))[0, 1])
        contributions.append({
            "feature": feature,
            "value": float(row[feature]),
            "reference": float(reference[feature]),
            "contribution": delta,
        })
    contributions.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    return LocalExplanation(
        probability=base_prob,
        baseline_probability=float(np.asarray(predict_proba(
            pd.DataFrame([reference[features].to_numpy(dtype=float)], columns=features)
        ))[0, 1]),
        contributions=contributions[:top_k],
        method=method_label,
    )


def shap_local_explanation(model, row: pd.Series, feature_names: list[str], top_k: int = 8) -> LocalExplanation:
    X = pd.DataFrame([row[feature_names].to_numpy(dtype=float)], columns=feature_names)
    values, expected = xgb_shap_matrix(model, X)
    items = []
    for index, feature in enumerate(feature_names):
        items.append({
            "feature": feature,
            "value": float(row[feature]),
            "contribution": float(values[0, index]),
        })
    items.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    probability = float(model.predict_proba(X)[0, 1])
    return LocalExplanation(
        probability=probability,
        baseline_probability=float(expected),
        contributions=items[:top_k],
        method="TreeSHAP (exact additive attributions)",
    )


def humanize_explanation(probability: float, contributions: list[dict], label_lookup) -> str:
    """Template generated from actual attributions; no canned narrative."""
    if not contributions:
        return "No attribution is available for this prediction."
    rising = [c for c in contributions if c["contribution"] > 0][:3]
    falling = [c for c in contributions if c["contribution"] < 0][:2]
    parts = []
    if rising:
        parts.append(
            "increased the risk: " + ", ".join(
                f"{label_lookup(c['feature'])} ({c['value']:.2f})" for c in rising
            )
        )
    if falling:
        parts.append(
            "reduced the risk: " + ", ".join(
                f"{label_lookup(c['feature'])} ({c['value']:.2f})" for c in falling
            )
        )
    direction = "elevated" if probability >= 0.5 else "below the alert threshold"
    return (
        f"Predicted failure probability {probability:.1%} is {direction}. "
        f"Strongest model attributions — " + "; ".join(parts) + ". "
        "These are model attributions, not confirmed physical causes."
    )
