"""Sensor forecasting on C-MAPSS trajectories.

Task: from the history available at cycle *t*, predict a sensor's value at
``t + h`` for horizons 1..10. Three statistical baselines (persistence, moving
average, exponential smoothing) are compared with a gradient-boosted model on
causal lag/rolling features.

Validation is strictly chronological: for every engine the first 70% of cycles
are training rows and the remaining cycles are test rows. No row is shuffled and
no future value enters a feature. MASE is reported alongside MAE/RMSE because it
is scale-free and compares against the naive one-step forecast.
"""

from __future__ import annotations

from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from sentinel.config import settings
from sentinel.logging_setup import get_logger

log = get_logger("models.forecast")

SENSORS: tuple[str, ...] = ("s2", "s3", "s4", "s11")
SENSOR_LABELS = {
    "s2": "Fan inlet pressure (P2)",
    "s3": "LPC outlet temperature (T24)",
    "s4": "LPC outlet pressure (P24)",
    "s11": "HPC outlet static pressure (Ps30)",
}
HORIZONS: tuple[int, ...] = tuple(range(1, 11))
REPORT_HORIZONS: tuple[int, ...] = (1, 5, 10)
TRAIN_FRACTION = 0.7
SES_ALPHA = 0.3
LAGS = (1, 2, 3, 5, 10)
WINDOWS = (5, 15, 30)
MODELS = ("persistence", "moving_average", "exponential_smoothing", "hist_gradient_boosting")


def build_forecast_features(frame: pd.DataFrame, sensor: str) -> pd.DataFrame:
    """Causal features for one sensor, computed per engine.

    Every rolling statistic is shifted by one cycle before the window is taken,
    so the value at ``t`` never contributes to its own feature vector.
    """
    parts: list[pd.DataFrame] = []
    for _, group in frame.groupby("asset_id", sort=True):
        series = group[sensor].astype(float)
        features = pd.DataFrame(index=group.index)
        for lag in LAGS:
            features[f"lag_{lag}"] = series.shift(lag)
        for window in WINDOWS:
            features[f"mean_{window}"] = (
                series.shift(1).rolling(window, min_periods=window).mean()
            )
            features[f"std_{window}"] = (
                series.shift(1).rolling(window, min_periods=window).std()
            )
        features["diff_1"] = series.diff(1)
        features["diff_5"] = series.diff(5)
        features["cycle"] = group["cycle"].astype(float)
        features["value"] = series

        level = float(series.iloc[0])
        smoothed = []
        for value in series:
            level = SES_ALPHA * float(value) + (1.0 - SES_ALPHA) * level
            smoothed.append(level)
        features["ses"] = smoothed
        parts.append(features)
    return pd.concat(parts).sort_index()


def chronological_masks(
    frame: pd.DataFrame, fraction: float = TRAIN_FRACTION
) -> tuple[pd.Series, pd.Series]:
    """Boolean train/test masks split by cycle position inside each engine."""
    train = pd.Series(False, index=frame.index)
    for _, group in frame.groupby("asset_id", sort=True):
        cutoff_index = max(1, int(len(group) * fraction)) - 1
        cutoff_cycle = group["cycle"].iloc[cutoff_index]
        train.loc[group.index] = group["cycle"] <= cutoff_cycle
    return train, ~train


def mase(actual: np.ndarray, predicted: np.ndarray, scale: float) -> float:
    if len(actual) == 0 or scale <= 0:
        return float("nan")
    return float(np.mean(np.abs(actual - predicted)) / scale)


def _metrics(actual: np.ndarray, predicted: np.ndarray, scale: float) -> dict:
    error = actual - predicted
    return {
        "mae": round(float(np.mean(np.abs(error))), 4),
        "rmse": round(float(np.sqrt(np.mean(error ** 2))), 4),
        "mase": round(mase(actual, predicted, scale), 4),
    }


def _naive_scale(frame: pd.DataFrame, sensor: str, train_mask: pd.Series) -> float:
    """Mean absolute one-step change on training rows, averaged over engines."""
    scales = []
    for _, group in frame.groupby("asset_id", sort=True):
        values = group.loc[train_mask.loc[group.index], sensor].astype(float)
        if len(values) > 1:
            scales.append(float(np.mean(np.abs(values.diff().dropna()))))
    return float(np.mean(scales)) if scales else 1.0


@dataclass
class ForecastResult:
    payload: dict
    models: dict[str, object]
    feature_names: list[str]


def train_sensor_forecast(
    frame: pd.DataFrame,
    *,
    sensors: tuple[str, ...] = SENSORS,
    horizons: tuple[int, ...] = HORIZONS,
    report_horizons: tuple[int, ...] = REPORT_HORIZONS,
) -> ForecastResult:
    frame = frame.sort_values(["asset_id", "cycle"]).reset_index(drop=True)
    train_mask, test_mask = chronological_masks(frame)
    feature_names: list[str] = []
    models: dict[str, object] = {}
    comparison: list[dict] = []
    examples: list[dict] = []

    for sensor in sensors:
        features = build_forecast_features(frame, sensor)
        # `ses` is causal (it only smooths values up to t), so it is a valid feature.
        feature_names = list(features.columns)
        scale = _naive_scale(frame, sensor, train_mask)
        targets = frame.groupby("asset_id")[sensor].shift(-1)
        # Recompute per horizon below; keep the frame index aligned.
        for horizon in horizons:
            target = frame.groupby("asset_id")[sensor].shift(-horizon)
            usable = target.notna()
            train_rows = train_mask & usable
            test_rows = test_mask & usable
            if train_rows.sum() < 50 or test_rows.sum() < 20:
                continue

            model = HistGradientBoostingRegressor(
                max_iter=120,
                learning_rate=0.08,
                min_samples_leaf=20,
                early_stopping=False,
                random_state=settings.random_seed,
            )
            # Trees cannot extrapolate a level beyond their training range, and the
            # held-out tail sits above the training range for degrading sensors.
            # Forecast the change from the current value instead, then add it back.
            delta = target - features["value"]
            model.fit(features.loc[train_rows, feature_names], delta[train_rows])
            models[f"{sensor}_h{horizon}"] = model

            actual = target[test_rows].to_numpy(dtype=float)
            predictions = {
                "persistence": features.loc[test_rows, "value"].to_numpy(dtype=float),
                "moving_average": features.loc[test_rows, "mean_15"].to_numpy(dtype=float),
                "exponential_smoothing": features.loc[test_rows, "ses"].to_numpy(dtype=float),
                "hist_gradient_boosting": (
                    features.loc[test_rows, "value"].to_numpy(dtype=float)
                    + model.predict(features.loc[test_rows, feature_names])
                ),
            }
            for name, predicted in predictions.items():
                valid = np.isfinite(predicted) & np.isfinite(actual)
                if valid.sum() < 20:
                    continue
                row = {
                    "sensor": sensor,
                    "label": SENSOR_LABELS.get(sensor, sensor),
                    "horizon": horizon,
                    "model": name,
                    **_metrics(actual[valid], predicted[valid], scale),
                }
                comparison.append(row)

        # Example: forecast the last ten cycles of the longest test engine.
        lengths = frame.groupby("asset_id")["cycle"].max()
        asset_id = int(lengths.idxmax())
        group = frame[frame["asset_id"] == asset_id].sort_values("cycle")
        origin_cycle = int(group["cycle"].iloc[-1]) - max(horizons)
        origin_rows = group[group["cycle"] == origin_cycle]
        if len(origin_rows) == 1:
            origin_index = origin_rows.index[0]
            origin_features = features.loc[[origin_index], feature_names]
            actual_series = group.set_index("cycle")[sensor]
            forecast_values, actual_values = [], []
            for horizon in horizons:
                model = models.get(f"{sensor}_h{horizon}")
                cycle = origin_cycle + horizon
                if model is None or cycle not in actual_series.index:
                    continue
                forecast_values.append(round(
                    float(origin_features["value"].iloc[0] + model.predict(origin_features)[0]), 4
                ))
                actual_values.append(round(float(actual_series.loc[cycle]), 4))
            if forecast_values:
                examples.append({
                    "sensor": sensor,
                    "label": SENSOR_LABELS.get(sensor, sensor),
                    "asset_id": f"FD001-{asset_id:03d}",
                    "origin_cycle": origin_cycle,
                    "horizons": list(range(1, len(forecast_values) + 1)),
                    "actual": actual_values,
                    "forecast": forecast_values,
                })

    best = []
    for sensor in sensors:
        for horizon in report_horizons:
            rows = [
                row for row in comparison
                if row["sensor"] == sensor and row["horizon"] == horizon
            ]
            if rows:
                best.append(min(rows, key=lambda row: row["mase"]))

    wins: dict[str, int] = {}
    for row in best:
        wins[row["model"]] = wins.get(row["model"], 0) + 1
    best_model = max(wins, key=wins.get) if wins else "n/a"
    best_mase = float(np.mean([row["mase"] for row in best])) if best else float("nan")
    persistence_rows = [
        row for row in comparison
        if row["model"] == "persistence"
        and row["horizon"] in report_horizons
    ]
    persistence_mase = (
        float(np.mean([row["mase"] for row in persistence_rows]))
        if persistence_rows else float("nan")
    )
    improvement = (
        (persistence_mase - best_mase) / persistence_mase * 100
        if persistence_mase and np.isfinite(persistence_mase) else float("nan")
    )

    payload = {
        "sensors": [
            {"key": sensor, "label": SENSOR_LABELS.get(sensor, sensor)} for sensor in sensors
        ],
        "horizons": list(report_horizons),
        "all_horizons": list(horizons),
        "models": list(MODELS),
        "validation": {
            "protocol": (
                "Chronological split inside every engine: first 70% of cycles train, "
                "remaining cycles test. Features at cycle t use only data up to t."
            ),
            "train_fraction": TRAIN_FRACTION,
            "train_rows": int(train_mask.sum()),
            "test_rows": int(test_mask.sum()),
            "units": int(frame["asset_id"].nunique()),
            "ses_alpha": SES_ALPHA,
        },
        "comparison": comparison,
        "best": best,
        "summary": {
            "best_model": best_model,
            "wins": wins,
            "mean_best_mase": round(best_mase, 4) if np.isfinite(best_mase) else None,
            "mean_persistence_mase": (
                round(persistence_mase, 4) if np.isfinite(persistence_mase) else None
            ),
            "improvement_vs_persistence_pct": (
                round(improvement, 2) if np.isfinite(improvement) else None
            ),
        },
        "example": {
            "asset_id": examples[0]["asset_id"] if examples else None,
            "origin_cycle": examples[0]["origin_cycle"] if examples else None,
            "series": examples,
        },
        "limitations": [
            "Forecasts are in operating cycles, not calendar time.",
            "C-MAPSS is simulated; real sensors need condition normalisation and maintenance context.",
            "Direct multi-horizon models are trained per horizon; they are not a recursive simulation.",
            "MASE is scaled by the naive one-step error on the training portion of each engine.",
        ],
    }

    joblib.dump(
        {"models": models, "feature_names": feature_names, "sensors": sensors},
        settings.model_dir / "cmapss_sensor_forecast.joblib",
    )
    log.info(
        "forecast models trained: %d fits, best=%s, mean MASE=%.3f",
        len(models), best_model, best_mase,
    )
    return ForecastResult(payload=payload, models=models, feature_names=feature_names)
