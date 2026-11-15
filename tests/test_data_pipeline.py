"""Data layer and feature-engineering tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sentinel.data.adapters.ai4i import AI4IAdapter
from sentinel.data.adapters.cmapss import CMAPSSAdapter, RAW_COLUMNS
from sentinel.data.validation import validate_dataset
from sentinel.features.pipeline import build_tabular_features, build_time_series_features


def synthetic_cmapss(units=(1, 2), cycles=6) -> pd.DataFrame:
    rows = []
    for unit in units:
        for cycle in range(1, cycles + 1):
            row = {"unit": unit, "cycle": cycle, "op1": 0.0, "op2": 0.0, "op3": 100.0}
            row.update({f"s{i}": float(i + cycle + unit) for i in range(1, 22)})
            rows.append(row)
    return pd.DataFrame(rows, columns=RAW_COLUMNS)


def test_ai4i_adapter_maps_to_canonical_schema():
    adapter = AI4IAdapter()
    if not adapter.is_available():
        pytest.skip("AI4I raw file not present; run python scripts/fetch_data.py")
    frame = adapter.load()
    assert len(frame) == 10_000
    assert {"row_id", "asset_id", "air_temp_k", "machine_failure"}.issubset(frame.columns)
    assert frame["machine_failure"].isin([0, 1]).all()
    # The five mode columns are *not* a strict partition of the union label:
    # 27 failure rows carry no mode and 42 mode rows carry no failure flag.
    # Documenting this mismatch is the point of the assertion below.
    modes = ["failure_twf", "failure_hdf", "failure_pwf", "failure_osf", "failure_rnf"]
    mode_any = (frame[modes].sum(axis=1) > 0).astype(int)
    mismatches = int((mode_any != frame["machine_failure"]).sum())
    assert 0 < mismatches < len(frame) * 0.01
    assert frame[modes].sum(axis=1).sum() == 373


def test_cmapss_rul_is_derived_from_cycle_position():
    adapter = CMAPSSAdapter(subset="FD001")
    canonical = adapter.canonicalize(synthetic_cmapss(cycles=6))
    unit_one = canonical[canonical["asset_id"] == 1].sort_values("cycle")
    assert unit_one["rul"].tolist() == [5.0, 4.0, 3.0, 2.0, 1.0, 0.0]
    assert canonical["asset_id"].nunique() == 2


def test_validation_flags_schema_errors_and_duplicate_keys():
    adapter = CMAPSSAdapter(subset="FD001")
    frame = adapter.canonicalize(synthetic_cmapss())
    report = validate_dataset(frame, adapter.schema)
    assert report.ok

    broken = frame.drop(columns=["s21"])
    missing_report = validate_dataset(broken, adapter.schema)
    assert not missing_report.ok
    assert any(issue.code == "missing_columns" for issue in missing_report.errors)

    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    duplicate_report = validate_dataset(duplicated, adapter.schema)
    assert any(issue.code == "duplicate_keys" for issue in duplicate_report.errors)


def test_quality_score_drops_with_more_issues():
    adapter = CMAPSSAdapter(subset="FD001")
    clean = adapter.canonicalize(synthetic_cmapss())
    good = validate_dataset(clean, adapter.schema)
    noisy = clean.copy()
    noisy.loc[0, "s2"] = np.nan
    noisy.loc[1, "s3"] = np.nan
    bad = validate_dataset(noisy, adapter.schema)
    assert bad.score < good.score


def test_rolling_features_are_causal_and_group_isolated():
    frame = pd.DataFrame({
        "asset_id": [1] * 40 + [2] * 40,
        "cycle": list(range(1, 41)) * 2,
        "s2": list(np.arange(40, dtype=float)) + list(np.arange(100, 140, dtype=float)),
    })
    features, specs = build_time_series_features(
        frame, ["s2"], windows=(5,), stats=("mean",),
        ema_spans=(), lags=(), add_deltas=False,
    )
    # cycle 10 (index 9) sees cycles 6..10 only -> values 5..9 -> mean 7.0
    assert features.loc[9, "s2_roll5_mean"] == pytest.approx(7.0)
    # early rows cannot have a complete window, so they stay missing
    assert pd.isna(features.loc[3, "s2_roll5_mean"])
    assert len(specs) == 1 and specs[0].params["causal"] is True

    mutated = frame.copy()
    mutated.loc[mutated["cycle"] > 10, "s2"] = 1e9
    mutated_features, _ = build_time_series_features(
        mutated, ["s2"], windows=(5,), stats=("mean",),
        ema_spans=(), lags=(), add_deltas=False,
    )
    past = features.loc[:9, "s2_roll5_mean"]
    future_mutated_past = mutated_features.loc[:9, "s2_roll5_mean"]
    pd.testing.assert_series_equal(past, future_mutated_past)

    # Engine 2's first window uses its own values, never engine 1's.
    assert features.loc[44, "s2_roll5_mean"] == pytest.approx(102.0)


def test_tabular_features_are_deterministic():
    raw = pd.DataFrame({
        "air_temp_k": [298.0, 300.0],
        "process_temp_k": [308.0, 310.0],
        "rotational_speed_rpm": [1500.0, 1200.0],
        "torque_nm": [40.0, 60.0],
        "tool_wear_min": [10.0, 200.0],
        "product_type": pd.Categorical(["L", "H"]),
    })
    featured, specs = build_tabular_features(raw)
    assert featured["temp_delta_k"].tolist() == [10.0, 10.0]
    assert featured["mechanical_power_w"].iloc[0] == pytest.approx(40 * 1500 * 2 * np.pi / 60)
    assert featured["type_L"].tolist() == [1, 0]
    assert featured["type_H"].tolist() == [0, 1]
    assert any(spec.kind == "physics" for spec in specs)
