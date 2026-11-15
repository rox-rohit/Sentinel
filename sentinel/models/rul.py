"""Remaining Useful Life regression on NASA C-MAPSS.

Protocol
--------
1. Feature engineering on the run-to-failure training trajectories using causal
   rolling statistics (see sentinel.features.pipeline).
2. Engine-wise split: 80 units train / 20 units validation. No engine appears on
   both sides, so no cycle-level leakage.
3. Candidate models are compared on the held-out engines (all cycles) using MAE,
   RMSE and the NASA asymmetric score.
4. The selected model is refit on all 100 training units and scored once on the
   official test trajectories (last recorded cycle per unit) against RUL_FDxxx.
5. Uncertainty comes from the empirical residual distribution on held-out engines.

RUL target: clipped at `settings.rul_clip` (125 cycles), because degradation is
not identifiable from sensor noise far from failure and unbounded targets let
healthy units dominate the loss.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from sentinel.config import settings
from sentinel.data.preprocessing import group_split
from sentinel.features.pipeline import build_time_series_features, model_feature_columns
from sentinel.logging_setup import get_logger
from sentinel.models.evaluation import regression_metrics
from sentinel.models.store import ModelArtifact, write_meta

log = get_logger("models.rul")


@dataclass
class RULResult:
    best_name: str
    comparison: list[dict]
    validation_metrics: dict
    official_test_metrics: dict
    residual_quantiles: dict
    feature_importance: list[dict]
    feature_names: list[str]
    warnings: list[str]
    residuals: np.ndarray
    predictions: pd.DataFrame  # asset_id, cycle, predicted_rul, actual_rul (where known)
    official_points: list[dict]
    fleet_features: pd.DataFrame  # held-out test trajectories with engineered features
    fleet_predictions: pd.DataFrame  # per-cycle RUL estimates for those trajectories
    fleet_history: pd.DataFrame  # complete held-out trajectories, including warm-up rows


def rul_candidates(seed: int) -> dict:
    return {
        "Ridge": Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=3.0))]),
        "RandomForest": RandomForestRegressor(
            n_estimators=180, min_samples_leaf=3, max_features=0.5,
            n_jobs=-1, random_state=seed,
        ),
        "XGBoost": XGBRegressor(
            n_estimators=450, max_depth=6, learning_rate=0.05, subsample=0.8,
            colsample_bytree=0.6, min_child_weight=3, reg_lambda=1.5,
            n_jobs=-1, random_state=seed, tree_method="hist",
        ),
    }


def clip_rul(values):
    return np.clip(np.asarray(values, dtype=float), 0.0, float(settings.rul_clip))


def build_rul_frames(adapter) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list]:
    """Return (train_features, test_features, feature_columns, feature_specs)."""
    train_raw = adapter.load()
    train_raw["rul_raw"] = train_raw["rul"]
    train_raw["rul"] = clip_rul(train_raw["rul_raw"])

    sensor_columns = [c for c in adapter.schema.sensor_columns if c in train_raw.columns]
    train_features, specs = build_time_series_features(
        train_raw, sensor_columns, group_col="asset_id", time_col="cycle"
    )
    features = model_feature_columns(
        specs, train_features,
        extra=["op1", "op2", "op3"],
    )

    test_raw = adapter.canonicalize(adapter.load_test())
    test_features, _ = build_time_series_features(
        test_raw,
        [c for c in adapter.schema.sensor_columns if c in test_raw.columns],
        group_col="asset_id",
        time_col="cycle",
    )
    return train_features, test_features, features, specs


def _last_cycle(frame: pd.DataFrame) -> pd.DataFrame:
    last = frame.groupby("asset_id")["cycle"].transform("max")
    return frame[frame["cycle"] == last].copy()


def _fit_and_predict(factory, X_train, y_train, X_eval):
    model = factory
    model.fit(X_train, y_train)
    return model, model.predict(X_eval)


def failure_risk_from_residuals(predicted_rul: float, residuals: np.ndarray, horizon: int) -> float:
    """P(true RUL <= horizon) approximated with the validation residual CDF."""
    if len(residuals) == 0:
        return 0.0
    implied = np.asarray(predicted_rul, dtype=float) + np.asarray(residuals, dtype=float)
    return float(np.clip(np.mean(implied <= horizon), 0.0, 1.0))


def residual_cdf(residuals: np.ndarray) -> np.ndarray:
    """Sorted residual sample for fast empirical CDF lookups."""
    return np.sort(np.asarray(residuals, dtype=float))


def horizon_risk_vector(predicted_rul, sorted_residuals: np.ndarray, horizon: int):
    """Vectorised P(true RUL <= horizon) using the empirical residual CDF."""
    query = float(horizon) - np.asarray(predicted_rul, dtype=float)
    return np.searchsorted(sorted_residuals, query, side="right") / max(1, len(sorted_residuals))


def train_rul_model(adapter, *, seed: int | None = None) -> RULResult:
    seed = seed if seed is not None else settings.random_seed
    train_features, test_features, features, _ = build_rul_frames(adapter)

    usable = train_features.dropna(subset=features + ["rul"]).copy()
    log.info("RUL training rows: %d / %d (rolled features need %d cycles)",
             len(usable), len(train_features), max(settings.rolling_windows))

    fit_frame, valid_frame, fit_units, valid_units = group_split(
        usable, group_col="asset_id", test_fraction=0.2, seed=seed
    )
    X_fit, y_fit = fit_frame[features], fit_frame["rul"]
    X_valid, y_valid = valid_frame[features], valid_frame["rul"]

    comparison = []
    fitted = {}
    for name, factory in rul_candidates(seed).items():
        model, pred = _fit_and_predict(factory, X_fit, y_fit, X_valid)
        metrics = regression_metrics(y_valid, clip_rul(pred))
        comparison.append({"model": name, **metrics})
        fitted[name] = model
        log.info("  %-14s MAE=%.2f RMSE=%.2f NASA=%.1f", name, metrics["mae"], metrics["rmse"],
                 metrics["nasa_score"])

    best = min(comparison, key=lambda row: (row["nasa_score"], row["rmse"]))
    best_name = best["model"]
    valid_pred = clip_rul(fitted[best_name].predict(X_valid))
    residuals = (y_valid.to_numpy(dtype=float) - valid_pred)
    residual_quantiles = {
        "p05": float(np.quantile(residuals, 0.05)),
        "p10": float(np.quantile(residuals, 0.10)),
        "p25": float(np.quantile(residuals, 0.25)),
        "p50": float(np.quantile(residuals, 0.50)),
        "p75": float(np.quantile(residuals, 0.75)),
        "p90": float(np.quantile(residuals, 0.90)),
        "p95": float(np.quantile(residuals, 0.95)),
        "std": float(np.std(residuals)),
        "count": int(len(residuals)),
        "source": f"held-out units {valid_units}",
    }

    # Refit on every training unit before the one-shot official test evaluation.
    final_model = rul_candidates(seed)[best_name]
    final_model.fit(usable[features], usable["rul"])

    official = _last_cycle(test_features.dropna(subset=features))
    official_pred = clip_rul(final_model.predict(official[features]))
    actual = official["rul"].to_numpy(dtype=float)
    official_metrics = regression_metrics(actual, official_pred)
    official_metrics["raw_unclipped_mae"] = float(
        np.mean(np.abs(np.clip(final_model.predict(official[features]), 0, None) - actual))
    )
    official_metrics["units"] = int(len(official_pred))
    official_points = [
        {
            "asset_id": f"FD001-{int(unit):03d}",
            "actual": round(float(actual[i]), 1),
            "predicted": round(float(official_pred[i]), 1),
            "lower": round(float(max(0.0, official_pred[i] + residual_quantiles["p10"])), 1),
            "upper": round(float(min(settings.rul_clip, official_pred[i] + residual_quantiles["p90"])), 1),
        }
        for i, unit in enumerate(official["asset_id"].to_numpy())
    ]

    # Fleet state comes from held-out test trajectories: units that are still in
    # service, never used for training. Predictions are genuinely out-of-sample.
    test_usable = test_features.dropna(subset=features).copy()
    fleet_pred = clip_rul(final_model.predict(test_usable[features]))
    fleet_predictions = test_usable[["asset_id", "cycle"]].assign(
        predicted_rul=fleet_pred,
        lower=np.clip(fleet_pred + residual_quantiles["p10"], 0, settings.rul_clip),
        upper=np.clip(fleet_pred + residual_quantiles["p90"], 0, settings.rul_clip),
    )

    all_pred = clip_rul(final_model.predict(usable[features]))
    predictions = usable[["asset_id", "cycle", "rul", "rul_raw"]].copy()
    # Fleet-level RUL uses out-of-fold predictions: every asset is scored by a
    # model that never saw that asset, so the fleet view is not in-sample.
    oof = cross_val_predict(
        rul_candidates(seed)[best_name], usable[features], usable["rul"],
        groups=usable["asset_id"], cv=GroupKFold(n_splits=5), n_jobs=1,
    )
    oof_pred = clip_rul(oof)
    predictions["predicted_rul"] = oof_pred
    predictions["lower"] = np.clip(oof_pred + residual_quantiles["p10"], 0, settings.rul_clip)
    predictions["upper"] = np.clip(oof_pred + residual_quantiles["p90"], 0, settings.rul_clip)

    sample = usable.sample(min(1200, len(usable)), random_state=seed)
    importance = permutation_importance(
        final_model, sample[features], sample["rul"],
        scoring="neg_mean_absolute_error", n_repeats=5, random_state=seed, n_jobs=-1,
    )
    feature_importance = sorted(
        [
            {"feature": f, "importance": float(m), "std": float(s)}
            for f, m, s in zip(features, importance.importances_mean, importance.importances_std)
        ],
        key=lambda row: row["importance"],
        reverse=True,
    )[:25]

    warnings = []
    if best["mae"] > 25:
        warnings.append("Hold-out MAE above 25 cycles: predictions are coarse for maintenance scheduling.")
    if abs(residual_quantiles["p50"]) > 5:
        warnings.append("Median residual is biased; the model systematically over- or under-predicts RUL.")

    ModelArtifact(
        name="cmapss_rul",
        task="rul_regression",
        model=final_model,
        feature_names=features,
        metadata={
            "dataset": "cmapss",
            "subset": getattr(adapter, "subset", "FD001"),
            "best_model": best_name,
            "comparison": comparison,
            "validation_metrics": best,
            "official_test_metrics": official_metrics,
            "residual_quantiles": residual_quantiles,
            "residual_sample": [round(float(v), 3) for v in residuals[::5]],
            "rul_clip": settings.rul_clip,
            "train_units": len(fit_units),
            "validation_units": len(valid_units),
            "feature_count": len(features),
            "feature_importance": feature_importance,
            "protocol": "engine-wise split; official test scored once at final cycle",
            "fleet_predictions": "out-of-fold (GroupKFold by engine), no asset scored in-sample",
            "limitations": [
                "C-MAPSS is simulated turbofan data; RUL is cycle-based, not calendar time.",
                f"Targets are clipped at {settings.rul_clip} cycles.",
                "Uncertainty is an empirical residual band, not a calibrated guarantee.",
            ],
        },
    ).save()

    payload = {
        "best_model": best_name,
        "comparison": comparison,
        "validation_metrics": best,
        "official_test_metrics": official_metrics,
        "residual_quantiles": residual_quantiles,
        "residual_sample": [round(float(v), 3) for v in residuals[::5]],
        "feature_importance": feature_importance,
        "rul_clip": settings.rul_clip,
        "protocol": "80/20 engine-wise split for selection; refit on all training units; official test once",
    }
    write_meta("rul", payload)

    return RULResult(
        best_name=best_name,
        comparison=comparison,
        validation_metrics=best,
        official_test_metrics=official_metrics,
        residual_quantiles=residual_quantiles,
        feature_importance=feature_importance,
        feature_names=features,
        warnings=warnings,
        residuals=residuals,
        predictions=predictions,
        official_points=official_points,
        fleet_features=test_usable,
        fleet_predictions=fleet_predictions,
        fleet_history=test_features,
    )
