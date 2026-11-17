"""Forecasting tests: chronological split, causal features, MASE and artifact."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sentinel.config import ARTIFACTS
from sentinel.models.forecast import (build_forecast_features, chronological_masks,
                                      mase, train_sensor_forecast)


def synthetic_frame(units: int = 3, cycles: int = 70) -> pd.DataFrame:
    rows = []
    for asset_id in range(1, units + 1):
        for cycle in range(1, cycles + 1):
            rows.append({
                "asset_id": asset_id,
                "cycle": cycle,
                "s2": 640.0 + asset_id * 2 + cycle * 0.1 + (cycle % 7) * 0.5,
                "s3": 1590.0 - cycle * 0.2,
                "s4": 550.0 + cycle * 0.05,
                "s11": 47.0 + cycle * 0.02,
            })
    return pd.DataFrame(rows)


def test_chronological_split_keeps_later_cycles_for_testing():
    frame = synthetic_frame(units=2, cycles=10)
    train, test = chronological_masks(frame, fraction=0.7)
    assert train.sum() + test.sum() == len(frame)
    for _, group in frame.groupby("asset_id"):
        train_cycles = group.loc[train.loc[group.index], "cycle"]
        test_cycles = group.loc[test.loc[group.index], "cycle"]
        assert train_cycles.max() < test_cycles.min()
        assert len(train_cycles) == 7


def test_features_never_use_the_current_or_future_value():
    frame = synthetic_frame(units=1, cycles=40)
    features = build_forecast_features(frame, "s2")
    # lag_1 at cycle t must equal the sensor at t-1, and is NaN at t=1.
    assert np.isnan(features.loc[frame.index[0], "lag_1"])
    assert features.loc[frame.index[5], "lag_1"] == frame.loc[frame.index[4], "s2"]
    # The rolling mean is shifted, so raising the value at t must not change mean_5 at t.
    before = features.loc[frame.index[20], "mean_5"]
    mutated = frame.copy()
    mutated.loc[frame.index[20], "s2"] = mutated.loc[frame.index[20], "s2"] + 500.0
    after = build_forecast_features(mutated, "s2").loc[frame.index[20], "mean_5"]
    assert before == after
    # ...but it must change the feature one cycle later.
    later = build_forecast_features(mutated, "s2").loc[frame.index[21], "mean_5"]
    assert later != features.loc[frame.index[21], "mean_5"]


def test_mase_is_scale_free():
    actual = np.array([10.0, 12.0, 14.0])
    predicted = np.array([10.0, 11.0, 15.0])
    assert mase(actual, predicted, scale=2.0) == pytest.approx((0 + 1 + 1) / 3 / 2)
    assert np.isnan(mase(actual, predicted, scale=0.0))


def test_training_produces_metrics_for_every_model_and_sensor():
    frame = synthetic_frame(units=4, cycles=200)
    result = train_sensor_forecast(
        frame, sensors=("s2", "s3"), horizons=(1, 3), report_horizons=(1, 3)
    )
    payload = result.payload
    assert len(payload["comparison"]) == 2 * 2 * 4
    assert {row["model"] for row in payload["comparison"]} == {
        "persistence", "moving_average", "exponential_smoothing", "hist_gradient_boosting",
    }
    assert all(np.isfinite(row["mase"]) for row in payload["comparison"])
    assert payload["summary"]["best_model"] in payload["models"]
    assert payload["validation"]["train_rows"] > 0
    assert payload["validation"]["test_rows"] > 0


@pytest.mark.skipif(
    not (ARTIFACTS / "snapshot.json").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)
def test_snapshot_contains_the_forecast_section():
    import json

    snapshot = json.loads((ARTIFACTS / "snapshot.json").read_text(encoding="utf-8"))
    forecast = snapshot["forecast"]
    assert forecast["comparison"]
    assert forecast["best"]
    assert forecast["example"]["series"]
    assert forecast["summary"]["best_model"]
