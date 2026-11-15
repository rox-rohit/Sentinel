"""Failure classification on UCI AI4I 2020.

Protocol: stratified 75/25 split, 5-fold stratified cross-validation on the
training split for model selection, threshold optimisation on out-of-fold
probabilities under an explicit cost model, then one evaluation on the held-out
25%. Model selection uses PR-AUC because failures are 3.4% of the data.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from sentinel.config import settings
from sentinel.features.pipeline import TABULAR_MODEL_FEATURES, build_tabular_features
from sentinel.logging_setup import get_logger
from sentinel.models.evaluation import (
    classification_metrics,
    expected_cost,
    threshold_curve,
)
from sentinel.models.store import ModelArtifact, write_meta

log = get_logger("models.classification")

FAILURE_MODE_COLUMNS = ["failure_twf", "failure_hdf", "failure_pwf", "failure_osf", "failure_rnf"]
FAILURE_MODE_LABELS = {
    "failure_twf": "Tool wear failure",
    "failure_hdf": "Heat dissipation failure",
    "failure_pwf": "Power failure",
    "failure_osf": "Overstrain failure",
    "failure_rnf": "Random failure",
}


@dataclass
class ClassificationResult:
    best_name: str
    comparison: list[dict]
    test_metrics: dict
    threshold: float
    calibration: dict
    feature_importance: list[dict]
    failure_modes: dict
    feature_names: list[str]
    warnings: list[str]
    fitted_model: object


def classifier_candidates(seed: int, scale_pos_weight: float) -> dict:
    return {
        "LogisticRegression": Pipeline([
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
        ]),
        "RandomForest": RandomForestClassifier(
            n_estimators=350, min_samples_leaf=2, max_features="sqrt",
            class_weight="balanced_subsample", n_jobs=-1, random_state=seed,
        ),
        "ExtraTrees": ExtraTreesClassifier(
            n_estimators=350, min_samples_leaf=2, max_features="sqrt",
            class_weight="balanced", n_jobs=-1, random_state=seed,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=350, learning_rate=0.06, max_leaf_nodes=31,
            l2_regularization=1.0, class_weight="balanced", random_state=seed,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.9,
            colsample_bytree=0.8, min_child_weight=2, reg_lambda=1.0,
            scale_pos_weight=scale_pos_weight, eval_metric="aucpr",
            n_jobs=-1, random_state=seed, tree_method="hist",
        ),
    }


def _feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    featured, _ = build_tabular_features(df)
    return featured


def _calibration_table(y_true, y_prob, bins: int = 8) -> list[dict]:
    frame = pd.DataFrame({"y": y_true, "p": y_prob})
    frame["bin"] = pd.qcut(frame["p"], q=bins, duplicates="drop")
    grouped = frame.groupby("bin", observed=True)
    return [
        {
            "bin_lower": float(interval.left),
            "bin_upper": float(interval.right),
            "mean_predicted": float(group["p"].mean()),
            "observed_rate": float(group["y"].mean()),
            "count": int(len(group)),
        }
        for interval, group in grouped
    ]


def _train_failure_modes(featured: pd.DataFrame, train_idx, test_idx, features, seed) -> dict:
    """Multi-label failure-mode models on the labels AI4I actually provides."""
    from sklearn.multiclass import OneVsRestClassifier

    X_train = featured.iloc[train_idx][features]
    X_test = featured.iloc[test_idx][features]
    results = []
    for column in FAILURE_MODE_COLUMNS:
        y_train = featured.iloc[train_idx][column]
        y_test = featured.iloc[test_idx][column]
        support_train, support_test = int(y_train.sum()), int(y_test.sum())
        entry = {
            "column": column,
            "label": FAILURE_MODE_LABELS[column],
            "train_support": support_train,
            "test_support": support_test,
            "status": "supported",
            "pr_auc": None,
            "recall": None,
            "precision": None,
            "note": "",
        }
        if support_train < 30:
            entry["status"] = "insufficient_support"
            entry["note"] = (
                f"Only {support_train} labelled cases in training; a model is not trained or exposed."
            )
            results.append(entry)
            continue
        model = OneVsRestClassifier(
            RandomForestClassifier(
                n_estimators=250, min_samples_leaf=2, class_weight="balanced",
                n_jobs=-1, random_state=seed,
            ),
            n_jobs=-1,
        )
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]
        metrics = classification_metrics(y_test, prob, threshold=0.5)
        entry.update({
            "pr_auc": metrics["pr_auc"],
            "recall": metrics["recall"],
            "precision": metrics["precision"],
            "status": "supported" if support_test >= 10 else "evaluated_low_support",
            "note": "Evaluated on the held-out 25% split.",
        })
        results.append(entry)
    return {
        "labels": results,
        "method": "One-vs-rest RandomForest per labelled failure mode",
        "limitations": [
            "Labels come from AI4I's simulated milling process, not from a plant CMMS.",
            "Modes can co-occur; the binary 'machine failure' label is their union.",
            "Modes with fewer than 30 training cases are not modelled, by design.",
        ],
    }


def train_failure_classifier(df: pd.DataFrame, *, seed: int | None = None) -> ClassificationResult:
    seed = seed if seed is not None else settings.random_seed
    featured = _feature_frame(df)
    features = [c for c in TABULAR_MODEL_FEATURES if c in featured.columns]
    X, y = featured[features], featured[settings.failure_target].astype(int)

    train_idx, test_idx = train_test_split(
        np.arange(len(featured)), test_size=settings.test_size, stratify=y, random_state=seed
    )
    X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
    X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
    imbalance = float((y_train == 0).sum() / max(1, (y_train == 1).sum()))
    log.info("AI4I split: %d train / %d test, positive rate %.2f%%",
             len(X_train), len(X_test), y.mean() * 100)

    cv = StratifiedKFold(n_splits=settings.cv_folds, shuffle=True, random_state=seed)
    comparison, fitted = [], {}
    for name, candidate in classifier_candidates(seed, imbalance).items():
        started = time.perf_counter()
        oof = cross_val_predict(clone(candidate), X_train, y_train, cv=cv,
                                method="predict_proba", n_jobs=1)[:, 1]
        cv_metrics = classification_metrics(y_train, oof, threshold=0.5)
        curve = threshold_curve(
            y_train, oof,
            fn_cost=settings.costs.false_negative_cost,
            fp_cost=settings.costs.false_positive_cost,
        )
        model = clone(candidate).fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]
        threshold = float(curve["best"]["threshold"])
        test_metrics = classification_metrics(y_test, prob, threshold=threshold)
        test_metrics["expected_cost"] = expected_cost(
            y_test, prob, threshold,
            fn_cost=settings.costs.false_negative_cost,
            fp_cost=settings.costs.false_positive_cost,
        )
        entry = {
            "model": name,
            "cv_pr_auc": cv_metrics["pr_auc"],
            "cv_roc_auc": cv_metrics["roc_auc"],
            "cv_recall_at_0.5": cv_metrics["recall"],
            "threshold": threshold,
            "test": test_metrics,
            "train_seconds": round(time.perf_counter() - started, 2),
        }
        comparison.append(entry)
        fitted[name] = model
        log.info("  %-22s CV PR-AUC=%.3f | test PR-AUC=%.3f recall=%.2f F1=%.2f",
                 name, cv_metrics["pr_auc"] or 0, test_metrics["pr_auc"] or 0,
                 test_metrics["recall"], test_metrics["f1"])

    best = max(comparison, key=lambda row: (row["cv_pr_auc"] or 0, -(row["test"]["expected_cost"])))
    best_name = best["model"]
    active = fitted[best_name]
    threshold = float(best["threshold"])
    test_prob = active.predict_proba(X_test)[:, 1]
    test_metrics = best["test"]

    calibration = {
        "brier_score": float(brier_score_loss(y_test, test_prob)),
        "brier_baseline_rate": float(brier_score_loss(y_test, np.full_like(test_prob, y.mean()))),
        "reliability": _calibration_table(y_test, test_prob),
        "note": "Reliability is measured on the held-out split; no post-hoc calibrator is applied.",
    }

    importance = permutation_importance(
        active, X_test, y_test, scoring="average_precision", n_repeats=8,
        random_state=seed, n_jobs=-1,
    )
    feature_importance = sorted(
        [
            {"feature": f, "importance": float(m), "std": float(s)}
            for f, m, s in zip(features, importance.importances_mean, importance.importances_std)
        ],
        key=lambda row: row["importance"],
        reverse=True,
    )

    failure_modes = _train_failure_modes(featured, train_idx, test_idx, features, seed)
    warnings = []
    if test_metrics["recall"] < 0.7:
        warnings.append("Recall below 0.70 at the cost-optimal threshold: failures may be missed.")
    if calibration["brier_score"] > calibration["brier_baseline_rate"]:
        warnings.append("Probabilities are not better than the base rate by Brier score.")

    ModelArtifact(
        name="ai4i_failure_classifier",
        task="failure_classification",
        model=active,
        feature_names=features,
        metadata={
            "dataset": "ai4i",
            "best_model": best_name,
            "threshold": threshold,
            "comparison": comparison,
            "test_metrics": test_metrics,
            "calibration": calibration,
            "feature_importance": feature_importance,
            "failure_modes": failure_modes,
            "cost_model": settings.costs.__dict__,
            "reference_medians": {k: float(v) for k, v in X_train.median().items()},
            "split": f"stratified {int((1 - settings.test_size) * 100)}/{int(settings.test_size * 100)}",
            "selection_metric": "cross-validated PR-AUC",
            "limitations": [
                "AI4I is a simulated milling process; failure semantics differ from a real CMMS.",
                "The threshold is tuned on training-fold out-of-fold probabilities.",
                "Costs in the optimisation are configurable assumptions, not measured plant data.",
            ],
        },
    ).save()

    payload = {
        "best_model": best_name,
        "threshold": threshold,
        "comparison": comparison,
        "test_metrics": test_metrics,
        "calibration": calibration,
        "feature_importance": feature_importance,
        "failure_modes": failure_modes,
        "warnings": warnings,
        "class_balance": {"positives": int(y.sum()), "rows": int(len(y))},
    }
    write_meta("failure_classification", payload)

    return ClassificationResult(
        best_name=best_name,
        comparison=comparison,
        test_metrics=test_metrics,
        threshold=threshold,
        calibration=calibration,
        feature_importance=feature_importance,
        failure_modes=failure_modes,
        feature_names=features,
        warnings=warnings,
        fitted_model=active,
    )
