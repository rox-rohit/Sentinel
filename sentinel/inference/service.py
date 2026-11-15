"""Inference services.

The API layer calls these; they own model loading, feature construction and
risk arithmetic. No HTTP concepts appear here.

Artifacts are read-only outputs of `python -m sentinel.pipelines.build`.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

from sentinel.config import settings
from sentinel.data.adapters.cmapss import SENSOR_COLUMNS
from sentinel.decision.optimizer import build_plan
from sentinel.features.pipeline import TABULAR_MODEL_FEATURES, build_tabular_features
from sentinel.logging_setup import get_logger
from sentinel.models.explain import humanize_explanation, occlusion_explanation
from sentinel.models.rul import horizon_risk_vector, residual_cdf
from sentinel.models.store import load_artifact

log = get_logger("inference")


class ArtifactUnavailable(RuntimeError):
    """Raised when the build pipeline has not produced the required artifacts."""


class SentinelService:
    def __init__(self, snapshot_path: Path | None = None) -> None:
        self.snapshot_path = snapshot_path or (settings.artifacts_dir / "snapshot.json")
        self._snapshot: dict | None = None
        self._snapshot_mtime = 0.0
        self._classifier = None
        self._rul = None
        self._lock = threading.Lock()

    # -- snapshot ---------------------------------------------------------
    def snapshot(self) -> dict:
        if not self.snapshot_path.exists():
            raise ArtifactUnavailable(
                "No platform snapshot found. Run: python -m sentinel.pipelines.build"
            )
        mtime = self.snapshot_path.stat().st_mtime
        if self._snapshot is None or mtime != self._snapshot_mtime:
            with self._lock:
                self._snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                self._snapshot_mtime = mtime
                log.info("loaded snapshot from %s", self.snapshot_path.name)
        return self._snapshot

    def clear_cache(self) -> None:
        self._snapshot = None
        self._classifier = None
        self._rul = None

    # -- models -----------------------------------------------------------
    def classifier(self):
        if self._classifier is None:
            self._classifier = load_artifact("ai4i_failure_classifier")
        return self._classifier

    def rul_model(self):
        if self._rul is None:
            self._rul = load_artifact("cmapss_rul")
        return self._rul

    # -- read helpers -----------------------------------------------------
    def assets(self) -> list[dict]:
        return self.snapshot()["assets"]

    def asset(self, asset_id: str) -> dict | None:
        target = asset_id.upper()
        for asset in self.assets():
            if asset["id"].upper() == target:
                return asset
        return None

    # -- failure classification ------------------------------------------
    def _classifier_input(self, payload: dict) -> pd.DataFrame:
        artifact = self.classifier()
        frame = pd.DataFrame([{
            "air_temp_k": float(payload["air_temp_k"]),
            "process_temp_k": float(payload["process_temp_k"]),
            "rotational_speed_rpm": float(payload["rotational_speed_rpm"]),
            "torque_nm": float(payload["torque_nm"]),
            "tool_wear_min": float(payload["tool_wear_min"]),
            "product_type": str(payload.get("product_type", "M")),
        }])
        frame["product_type"] = frame["product_type"].astype("category")
        featured, _ = build_tabular_features(frame)
        missing = [c for c in artifact.feature_names if c not in featured.columns]
        if missing:
            raise ArtifactUnavailable(f"Feature contract mismatch; missing {missing}")
        return featured[artifact.feature_names]

    def predict_failure(self, payload: dict) -> dict:
        artifact = self.classifier()
        X = self._classifier_input(payload)
        probability = float(artifact.model.predict_proba(X)[0, 1])
        threshold = float(artifact.metadata.get("threshold", 0.5))
        band = "high" if probability >= threshold else "elevated" if probability >= threshold * 0.5 else "low"
        return {
            "probability": round(probability, 4),
            "threshold": round(threshold, 4),
            "alert": probability >= threshold,
            "risk_band": band,
            "model": artifact.metadata.get("best_model", "unknown"),
            "dataset": "ai4i",
            "inputs": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in payload.items()},
        }

    def explain_failure(self, payload: dict) -> dict:
        artifact = self.classifier()
        X = self._classifier_input(payload)
        reference_values = artifact.metadata.get("reference_medians", {})
        reference = pd.Series({name: reference_values.get(name, 0.0) for name in X.columns})
        row = X.iloc[0]
        explanation = occlusion_explanation(artifact.model.predict_proba, row, reference)
        from sentinel.features.pipeline import SENSOR_LABELS_AI4I

        return {
            "probability": round(explanation.probability, 4),
            "baseline_probability": round(explanation.baseline_probability, 4),
            "method": explanation.method,
            "contributions": [
                {
                    "feature": c["feature"],
                    "label": SENSOR_LABELS_AI4I.get(c["feature"], c["feature"]),
                    "value": round(c["value"], 3),
                    "contribution": round(c["contribution"], 4),
                }
                for c in explanation.contributions
            ],
            "narrative": humanize_explanation(
                explanation.probability, explanation.contributions,
                lambda f: SENSOR_LABELS_AI4I.get(f, f),
            ),
            "caveat": "Attribution describes model behaviour, not confirmed physical causation.",
        }

    # -- RUL ---------------------------------------------------------------
    def predict_rul(self, readings: list[dict]) -> dict:
        if len(readings) < max(settings.rolling_windows):
            raise ValueError(
                f"At least {max(settings.rolling_windows)} cycles are required to build rolling features."
            )
        frame = pd.DataFrame(readings)
        frame["asset_id"] = 0
        for column in ("op1", "op2", "op3"):
            if column not in frame.columns:
                frame[column] = 0.0
        missing = [c for c in SENSOR_COLUMNS if c not in frame.columns]
        if missing:
            raise ValueError(f"Missing sensor columns in the sequence: {missing}")
        if "cycle" not in frame.columns:
            frame["cycle"] = np.arange(1, len(frame) + 1)
        frame = frame.sort_values("cycle").reset_index(drop=True)

        from sentinel.features.pipeline import build_time_series_features

        featured, _ = build_time_series_features(
            frame, list(SENSOR_COLUMNS), group_col="asset_id", time_col="cycle"
        )
        artifact = self.rul_model()
        latest = featured.dropna(subset=artifact.feature_names).tail(1)
        if latest.empty:
            raise ValueError("Not enough history to produce a complete feature vector.")
        prediction = float(np.clip(
            artifact.model.predict(latest[artifact.feature_names])[0], 0, settings.rul_clip
        ))
        residuals = np.asarray(
            artifact.metadata.get("residual_sample", []), dtype=float
        )
        quantiles = artifact.metadata.get("residual_quantiles", {})
        risks = {}
        if len(residuals) > 10:
            sorted_residuals = residual_cdf(residuals)
            for horizon in settings.horizon_cycles:
                risks[str(horizon)] = round(
                    float(horizon_risk_vector([prediction], sorted_residuals, horizon)[0]), 4
                )
        return {
            "predicted_rul": round(prediction, 1),
            "lower": round(max(0.0, prediction + float(quantiles.get("p10", -20))), 1),
            "upper": round(min(float(settings.rul_clip), prediction + float(quantiles.get("p90", 20))), 1),
            "horizon_risk": risks,
            "cycles_supplied": int(len(readings)),
            "model": artifact.metadata.get("best_model", "unknown"),
            "clip": settings.rul_clip,
            "note": "RUL is in operating cycles and is not a guaranteed failure date.",
        }

    # -- decision ----------------------------------------------------------
    def optimize_maintenance(self, budget: float, assets_input: list[dict] | None = None) -> dict:
        if assets_input:
            rows = assets_input
        else:
            rows = [
                {
                    "asset_id": asset["id"],
                    "criticality": asset["criticality"],
                    "failure_risk": asset["rul"]["horizon_risk"].get("30", 0.0),
                    "predicted_rul": asset["rul"]["estimate"],
                }
                for asset in self.assets()
            ]
        plan = build_plan(rows, budget=budget)
        return {
            "budget": plan.budget,
            "spent": plan.spent,
            "expected_avoided_loss": plan.expected_avoided_loss,
            "expected_downtime_hours": plan.expected_downtime_hours,
            "selected": plan.selected,
            "deferred": plan.deferred[:40],
            "scenarios": plan.scenarios,
            "assumptions": plan.assumptions,
            "notes": plan.notes,
        }

    # -- status ------------------------------------------------------------
    def system_status(self) -> dict:
        snapshot = self.snapshot()
        return {
            "status": "ok",
            "product": "SENTINEL",
            "snapshot": {
                "path": str(self.snapshot_path),
                "generated_at": snapshot["meta"]["generated_at"],
                "build_version": snapshot["meta"]["build_version"],
                "age_seconds": round(time.time() - self.snapshot_path.stat().st_mtime, 1),
                "size_kb": round(self.snapshot_path.stat().st_size / 1024, 1),
            },
            "artifacts": {
                "classifier": (settings.model_dir / "ai4i_failure_classifier.joblib").exists(),
                "rul": (settings.model_dir / "cmapss_rul.joblib").exists(),
            },
            "datasets": snapshot["meta"]["dataset_versions"],
        }


_service: SentinelService | None = None


def get_service() -> SentinelService:
    global _service
    if _service is None:
        _service = SentinelService()
    return _service
