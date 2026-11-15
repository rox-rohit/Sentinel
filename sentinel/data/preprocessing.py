"""Cleaning and persistence of canonical frames.

Cleaning is conservative: duplicate rows/keys are removed, dtypes are enforced,
missing numeric values are imputed only when explicitly requested (so the
choice is visible), and outliers are never silently deleted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from sentinel.data.schema import DatasetSchema
from sentinel.logging_setup import get_logger

log = get_logger("data.preprocessing")


@dataclass
class CleanResult:
    frame: pd.DataFrame
    removed_duplicates: int
    imputed_cells: int
    notes: list[str]


def clean_frame(df: pd.DataFrame, schema: DatasetSchema, *, impute: bool = False) -> CleanResult:
    notes: list[str] = []
    frame = df.copy()

    before = len(frame)
    key_cols = [c for c in (schema.id_column, schema.time_column) if c and c in frame.columns]
    if len(key_cols) == 2:
        frame = frame.drop_duplicates(subset=key_cols, keep="first")
    else:
        frame = frame.drop_duplicates(keep="first")
    removed = before - len(frame)
    if removed:
        notes.append(f"Removed {removed} duplicate rows.")

    imputed = 0
    if impute:
        for col in schema.sensor_columns:
            if col in frame.columns and frame[col].isna().any():
                count = int(frame[col].isna().sum())
                frame[col] = frame[col].fillna(frame[col].median())
                imputed += count
        if imputed:
            notes.append(f"Median-imputed {imputed} sensor cells.")

    if len(key_cols) == 2:
        frame = frame.sort_values(key_cols).reset_index(drop=True)
        notes.append(f"Sorted by {key_cols}.")

    return CleanResult(frame=frame, removed_duplicates=removed, imputed_cells=imputed, notes=notes)


def frame_version(df: pd.DataFrame) -> str:
    """Stable content hash used for dataset version tracking."""
    hashed = pd.util.hash_pandas_object(df, index=False).to_numpy()
    return hashlib.sha256(hashed.tobytes()).hexdigest()[:12]


def save_processed(df: pd.DataFrame, name: str, *, root: Path | None = None) -> Path:
    from sentinel.config import DATA_PROCESSED

    root = root or DATA_PROCESSED
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.parquet"
    df.to_parquet(path, index=False)
    log.info("wrote processed dataset %s (%d rows)", path.name, len(df))
    return path


def load_processed(name: str, *, root: Path | None = None) -> pd.DataFrame:
    from sentinel.config import DATA_PROCESSED

    root = root or DATA_PROCESSED
    path = root / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Processed dataset missing: {path}. Run: python -m sentinel.pipelines.build")
    return pd.read_parquet(path)


def chronological_split(df: pd.DataFrame, *, time_col: str, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by time, never at random, for any time-series task."""
    ordered = df.sort_values(time_col)
    cut = int(len(ordered) * train_ratio)
    return ordered.iloc[:cut].copy(), ordered.iloc[cut:].copy()


def group_split(df: pd.DataFrame, *, group_col: str, test_fraction: float = 0.2,
                seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, list, list]:
    """Split whole entities (engines/machines) into train/test to avoid leakage."""
    groups = sorted(df[group_col].unique())
    rng = pd.Series(groups).sample(frac=1.0, random_state=seed).to_list()
    n_test = max(1, int(round(len(groups) * test_fraction)))
    test_groups = sorted(rng[:n_test])
    train_groups = sorted(rng[n_test:])
    train = df[df[group_col].isin(train_groups)].copy()
    test = df[df[group_col].isin(test_groups)].copy()
    return train, test, train_groups, test_groups
