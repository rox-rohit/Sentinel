"""Unsupervised anomaly detection on C-MAPSS sensor windows.

Three detectors with different inductive biases:
  * IsolationForest — multivariate isolation on the full rolling feature set.
  * LocalOutlierFactor (novelty mode) — local density on a compact degradation subset.
  * PCA reconstruction error — deviation from the healthy correlation structure.

All three are fitted only on early-life ("healthy") windows, so the score means
"distance from healthy behaviour", not "failure". Severity bands are percentile
cuts of the healthy score distribution (see DECISIONS D-010).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from sentinel.config import settings
from sentinel.logging_setup import get_logger

log = get_logger("models.anomaly")

SEVERITY_BANDS = (
    ("normal", 0.90),
    ("low", 0.97),
    ("medium", 0.995),
    ("high", 0.999),
)


@dataclass
class AnomalyResult:
    frame: pd.DataFrame  # asset_id, cycle, score, severity, detector scores
    thresholds: dict
    summary: dict
    sensor_ranges: dict


def _healthy_mask(frame: pd.DataFrame) -> pd.Series:
    return (frame["cycle"] >= max(settings.rolling_windows)) & (
        frame["cycle"] <= settings.healthy_cycle_limit + 30
    )


def compact_features(frame: pd.DataFrame) -> list[str]:
    rolling = [c for c in frame.columns if "_roll15_std" in c]
    deltas = [c for c in frame.columns if c.endswith("_delta1")]
    return rolling[:12] + deltas[:6]


def _norm(scores: np.ndarray, reference: np.ndarray) -> np.ndarray:
    scale = np.quantile(reference, 0.99)
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0
    return np.clip(scores / scale, 0.0, 10.0)


def fit_anomaly_detectors(
    frame: pd.DataFrame,
    *,
    feature_names: list[str],
    score_frame: pd.DataFrame | None = None,
    seed: int | None = None,
) -> AnomalyResult:
    """Fit on early-life rows of `frame`, then score `score_frame` (or `frame`).

    `score_frame` lets the fleet view score held-out trajectories with detectors
    that only ever saw healthy training behaviour.
    """
    seed = seed if seed is not None else settings.random_seed
    fit_data = frame.dropna(subset=feature_names).copy()
    healthy = fit_data[_healthy_mask(fit_data)]
    if len(healthy) < 100:
        raise ValueError("Not enough healthy windows to fit anomaly detectors.")

    data = (score_frame if score_frame is not None else frame).dropna(subset=feature_names).copy()
    compact = compact_features(fit_data)
    compact = [c for c in compact if c in fit_data.columns]
    scaler = StandardScaler().fit(healthy[compact])
    healthy_compact = scaler.transform(healthy[compact])
    all_compact = scaler.transform(data[compact])

    iso = IsolationForest(n_estimators=250, contamination=0.02, random_state=seed, n_jobs=-1)
    iso.fit(healthy[feature_names])
    iso_all = -iso.score_samples(data[feature_names])
    iso_healthy = -iso.score_samples(healthy[feature_names])

    lof = LocalOutlierFactor(n_neighbors=25, novelty=True, contamination=0.02, n_jobs=-1)
    lof.fit(healthy_compact)
    lof_all = -lof.score_samples(all_compact)
    lof_healthy = -lof.score_samples(healthy_compact)

    pca = PCA(n_components=min(8, healthy_compact.shape[1]), random_state=seed).fit(healthy_compact)
    pca_all = np.sqrt(((all_compact - pca.inverse_transform(pca.transform(all_compact))) ** 2).sum(axis=1))
    pca_healthy = np.sqrt(((healthy_compact - pca.inverse_transform(pca.transform(healthy_compact))) ** 2).sum(axis=1))

    norm_iso = _norm(iso_all, iso_healthy)
    norm_lof = _norm(lof_all, lof_healthy)
    norm_pca = _norm(pca_all, pca_healthy)
    ensemble = (norm_iso + norm_lof + norm_pca) / 3.0

    result = data[["asset_id", "cycle"]].copy()
    result["isolation_forest"] = norm_iso
    result["lof"] = norm_lof
    result["pca_reconstruction"] = norm_pca
    result["score"] = ensemble

    iso_healthy_scores = -iso.score_samples(healthy[feature_names])
    healthy_ensemble = (
        _norm(iso_healthy_scores, iso_healthy)
        + _norm(-lof.score_samples(healthy_compact), lof_healthy)
        + _norm(np.sqrt(((healthy_compact - pca.inverse_transform(pca.transform(healthy_compact))) ** 2).sum(axis=1)), pca_healthy)
    ) / 3.0
    thresholds = {name: float(np.quantile(healthy_ensemble, q)) for name, q in SEVERITY_BANDS}
    result["severity"] = pd.cut(
        result["score"],
        bins=[-np.inf, thresholds["normal"], thresholds["low"], thresholds["medium"],
              thresholds["high"], np.inf],
        labels=["normal", "low", "medium", "high", "critical"],
    ).astype(str)

    sensor_ranges = {
        c: {"mean": float(healthy[c].mean()), "std": float(healthy[c].std() or 1.0)}
        for c in feature_names[:80]
    }
    summary = {
        "fit_rows": int(len(healthy)),
        "scored_rows": int(len(result)),
        "healthy_score_mean": float(healthy_ensemble.mean()),
        "healthy_score_median": float(np.median(healthy_ensemble)),
        "ensemble": "mean of p99-normalised IsolationForest, LOF and PCA reconstruction error",
        "severity_distribution": {k: int(v) for k, v in result["severity"].value_counts().items()},
        "thresholds": thresholds,
        "limitations": [
            "Scores measure distance from an early-life healthy baseline, not probability of failure.",
            "Thresholds are percentile cuts of that baseline and are dataset-specific.",
            "FD001 has a single operating condition; FD002/FD004 would need condition normalisation.",
        ],
    }
    log.info("anomaly ensemble fitted on %d healthy rows; %d rows scored", len(healthy), len(result))
    return AnomalyResult(frame=result, thresholds=thresholds, summary=summary,
                         sensor_ranges=sensor_ranges)
