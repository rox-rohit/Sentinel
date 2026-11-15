"""Leakage-safe feature engineering.

Rules enforced here:
  * rolling/EMA features are causal (past-only), never centred;
  * the frame must be sorted by (group, time) — unsorted input is rejected;
  * group boundaries are respected so an engine never sees another engine's past;
  * every generated feature is described in a FeatureSpec so the model card can
    document exactly what was fed to it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from sentinel.config import settings
from sentinel.logging_setup import get_logger

log = get_logger("features")

FEATURE_VERSION = "fs-v1"
MAX_WINDOW = max(settings.rolling_windows)


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    kind: str
    source: str | None
    params: dict = field(default_factory=dict)
    version: str = FEATURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _require_sorted(df: pd.DataFrame, group_col: str, time_col: str) -> None:
    """Reject frames whose time axis is not ordered inside each entity.

    A global monotonic check is wrong for grouped series (the clock restarts per
    engine), so ordering is verified per entity.
    """
    for _, group in df.groupby(group_col, sort=False):
        if not group[time_col].is_monotonic_increasing:
            raise ValueError(
                "Feature engineering requires rows sorted by time inside each entity; "
                "unsorted input can leak future observations into rolling statistics."
            )
    starts = df[group_col].ne(df[group_col].shift()).sum()
    if starts != df[group_col].nunique():
        raise ValueError("Rows for each entity must be contiguous; re-sort by (group, time).")


def build_time_series_features(
    df: pd.DataFrame,
    sensor_cols: list[str] | tuple[str, ...],
    *,
    group_col: str = "asset_id",
    time_col: str = "cycle",
    windows: tuple[int, ...] | None = None,
    stats: tuple[str, ...] | None = None,
    ema_spans: tuple[int, ...] | None = None,
    lags: tuple[int, ...] | None = None,
    add_deltas: bool = True,
) -> tuple[pd.DataFrame, list[FeatureSpec]]:
    """Add causal rolling/lag/EMA/delta features and return their specifications."""
    # Explicit empty tuples mean "no features of this kind"; only None falls back
    # to the configured defaults.
    windows = settings.rolling_windows if windows is None else windows
    stats = settings.rolling_stats if stats is None else stats
    ema_spans = settings.ema_spans if ema_spans is None else ema_spans
    lags = settings.lags if lags is None else lags

    frame = df.sort_values([group_col, time_col]).reset_index(drop=True)
    _require_sorted(frame, group_col, time_col)

    sensors = [c for c in sensor_cols if c in frame.columns]
    if not sensors:
        raise ValueError("No sensor columns available for feature engineering.")

    specs: list[FeatureSpec] = []
    out = frame.copy()
    grouped = out.groupby(group_col, sort=False)

    for window in windows:
        rolling = grouped[sensors].rolling(window, min_periods=window)
        parts: dict[str, pd.Series] = {}
        for stat in stats:
            result = getattr(rolling, stat)()
            result.index = result.index.droplevel(0)
            result = result.sort_index()
            for sensor in sensors:
                name = f"{sensor}_roll{window}_{stat}"
                parts[name] = result[sensor]
                specs.append(FeatureSpec(name, f"rolling_{stat}", sensor,
                                         {"window": window, "min_periods": window, "causal": True}))
        out = pd.concat([out, pd.DataFrame(parts, index=out.index)], axis=1)

    for span in ema_spans:
        ema = grouped[sensors].ewm(span=span, adjust=False).mean()
        ema.index = ema.index.droplevel(0)
        ema = ema.sort_index()
        for sensor in sensors:
            name = f"{sensor}_ema{span}"
            out[name] = ema[sensor]
            specs.append(FeatureSpec(name, "ema", sensor, {"span": span, "causal": True}))

    for lag in lags:
        shifted = grouped[sensors].shift(lag)
        for sensor in sensors:
            name = f"{sensor}_lag{lag}"
            out[name] = shifted[sensor]
            specs.append(FeatureSpec(name, "lag", sensor, {"lag": lag}))

    if add_deltas:
        diff_parts: dict[str, pd.Series] = {}
        for lag in sorted(set(lags)):
            diff = grouped[sensors].diff(lag)
            for sensor in sensors:
                name = f"{sensor}_delta{lag}"
                diff_parts[name] = diff[sensor]
                specs.append(FeatureSpec(name, "delta", sensor, {"lag": lag}))
        out = pd.concat([out, pd.DataFrame(diff_parts, index=out.index)], axis=1)

    log.info("built %d features over %d sensors (%d rows)", len(specs), len(sensors), len(out))
    return out, specs


def model_feature_columns(feature_specs: list[FeatureSpec], frame: pd.DataFrame,
                          *, extra: list[str] | None = None,
                          drop_constant: bool = True) -> list[str]:
    names = [s.name for s in feature_specs if s.name in frame.columns]
    names += [c for c in (extra or []) if c in frame.columns]
    if drop_constant:
        names = [c for c in names if frame[c].nunique(dropna=True) > 1]
    return names


def build_tabular_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[FeatureSpec]]:
    """Physics-informed tabular features for the AI4I process dataset.

    These are deterministic transforms of the recorded channels, not invented
    labels: temperature difference, spindle mechanical power, and wear fraction.
    """
    frame = df.copy()
    specs: list[FeatureSpec] = []

    frame["temp_delta_k"] = frame["process_temp_k"] - frame["air_temp_k"]
    specs.append(FeatureSpec("temp_delta_k", "difference", "process_temp_k - air_temp_k"))

    frame["mechanical_power_w"] = frame["torque_nm"] * frame["rotational_speed_rpm"] * (2 * np.pi / 60.0)
    specs.append(FeatureSpec("mechanical_power_w", "physics", "torque_nm * rpm * 2pi/60"))

    frame["overstrain_index"] = frame["tool_wear_min"] * frame["torque_nm"]
    specs.append(FeatureSpec("overstrain_index", "interaction", "tool_wear_min * torque_nm"))

    frame["thermal_efficiency"] = frame["temp_delta_k"] / frame["rotational_speed_rpm"].replace(0, np.nan)
    specs.append(FeatureSpec("thermal_efficiency", "ratio", "temp_delta_k / rpm"))

    # Product quality variant is categorical; one-hot keeps it usable by linear models.
    for letter in ("L", "M", "H"):
        col = f"type_{letter}"
        frame[col] = (frame["product_type"].astype(str) == letter).astype("int8")
        specs.append(FeatureSpec(col, "one_hot", "product_type", {"category": letter}))
    return frame, specs


TABULAR_MODEL_FEATURES = [
    "air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min",
    "temp_delta_k", "mechanical_power_w", "overstrain_index", "thermal_efficiency",
    "type_L", "type_M", "type_H",
]

SENSOR_LABELS_AI4I = {
    "air_temp_k": "Air temperature",
    "process_temp_k": "Process temperature",
    "rotational_speed_rpm": "Rotational speed",
    "torque_nm": "Torque",
    "tool_wear_min": "Tool wear",
    "temp_delta_k": "Process-air temperature delta",
    "mechanical_power_w": "Mechanical power",
    "overstrain_index": "Tool-wear × torque (overstrain proxy)",
    "thermal_efficiency": "Thermal gradient per rpm",
    "type_L": "Product type L",
    "type_M": "Product type M",
    "type_H": "Product type H",
}
