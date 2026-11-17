"""Reproducible end-to-end build.

    python -m sentinel.pipelines.build

Runs ingestion -> validation -> preprocessing -> features -> models -> decision
outputs -> snapshot export. Every artefact the UI reads is produced here.
"""

from __future__ import annotations

import json
import platform
import time
import hashlib
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy import delete

from sentinel import BUILD_NAME, __version__
from sentinel.config import GENERATED, settings
from sentinel.data.adapters import load_adapter
from sentinel.data.preprocessing import clean_frame, frame_version, save_processed
from sentinel.data.validation import validate_dataset
from sentinel.decision.health import weights_payload
from sentinel.decision.optimizer import build_plan
from sentinel.eda import build_eda
from sentinel.features.pipeline import build_time_series_features, model_feature_columns
from sentinel.logging_setup import get_logger
from sentinel.models.anomaly import fit_anomaly_detectors
from sentinel.models.classification import train_failure_classifier
from sentinel.models.explain import humanize_explanation, occlusion_explanation
from sentinel.models.forecast import train_sensor_forecast
from sentinel.models.evaluation import psi, psi_status
from sentinel.models.rul import build_rul_frames, train_rul_model
from sentinel.models.store import read_meta
from sentinel.pipelines.assemble import assemble_assets, build_alerts
from sentinel.pipelines.snapshot import compose_snapshot, sanitize
from sentinel.features.pipeline import SENSOR_LABELS_AI4I, build_tabular_features
from sentinel.store.db import (AlertRecord, DatasetRecord, ModelRecord, init_db,
                               list_datasets, list_models, session_scope)

log = get_logger("pipelines.build")
SNAPSHOT = settings.artifacts_dir / "snapshot.json"
REPLAY = settings.artifacts_dir / "replay.parquet"


def _register_dataset(adapter, frame: pd.DataFrame, quality: dict, path) -> None:
    version = frame_version(frame)
    with session_scope() as session:
        existing = session.scalars(
            select(DatasetRecord).where(
                DatasetRecord.name == adapter.info.name, DatasetRecord.version == version
            )
        ).first()
        if existing:
            return
        session.add(DatasetRecord(
            name=adapter.info.name,
            display_name=adapter.info.display_name,
            version=version,
            rows=int(len(frame)),
            columns=int(frame.shape[1]),
            path=str(path),
            quality_json=json.dumps(quality, default=str),
            schema_json=json.dumps(adapter.describe(), default=str),
            source_url=adapter.info.source_url,
        ))
    log.info("registered dataset %s@%s", adapter.info.name, version)


def _prune_registry() -> None:
    """Keep one row per (name, version); older duplicate rows add no information."""
    with session_scope() as session:
        rows = session.scalars(select(ModelRecord).order_by(ModelRecord.id.desc())).all()
        seen: set[tuple[str, str]] = set()
        removed = 0
        for row in rows:
            key = (row.name, row.version)
            if key in seen:
                session.delete(row)
                removed += 1
            else:
                seen.add(key)
    if removed:
        log.info("pruned %d duplicate registry rows", removed)


def _register_model(name: str, task: str, dataset: str, algorithm: str, metrics: dict,
                    params: dict, status: str = "active") -> None:
    def stable(value):
        """Drop wall-clock fields: a timing must not create a new model version."""
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items() if k != "train_seconds"}
        if isinstance(value, list):
            return [stable(item) for item in value]
        if isinstance(value, float):
            # Last-bit float jitter must not mint a new model version.
            return round(value, 6)
        return value

    digest = hashlib.sha1(
        json.dumps(stable(metrics), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:6]
    version = f"{datetime.now(timezone.utc):%Y.%m.%d}-{digest}"
    with session_scope() as session:
        existing = session.scalars(
            select(ModelRecord).where(
                ModelRecord.name == name, ModelRecord.version == version
            )
        ).all()
        if existing:
            # Keep one row per (name, version); metrics are identical by construction.
            for duplicate in existing[1:]:
                session.delete(duplicate)
            return
        session.add(ModelRecord(
            name=name, task=task, dataset=dataset, version=version, algorithm=algorithm,
            status=status, metrics_json=json.dumps(metrics, default=str),
            params_json=json.dumps(params, default=str),
            artifact_path=str(settings.model_dir / f"{name}.joblib"),
        ))
    log.info("registered model %s@%s (%s)", name, version, status)


def _export_replay(fleet_frame: pd.DataFrame) -> dict:
    """Write the recorded per-cycle trajectories streamed by the replay service."""
    from sentinel.replay.service import REPLAY_SENSORS

    sensors = [sensor for sensor in REPLAY_SENSORS if sensor in fleet_frame.columns]
    columns = [
        "asset_id", "cycle", "predicted_rul", "lower", "upper", "risk_30",
        "score", "severity", "health", *sensors,
    ]
    missing = [column for column in columns if column not in fleet_frame.columns]
    if missing:
        log.warning("replay export skipped; missing columns %s", missing)
        return {"units": 0, "cycles": 0}
    replay_frame = (
        fleet_frame[columns]
        .rename(columns={"score": "anomaly_score", "severity": "anomaly_severity"})
        .sort_values(["asset_id", "cycle"])
        .reset_index(drop=True)
    )
    replay_frame.to_parquet(REPLAY, index=False)
    summary = {
        "units": int(replay_frame["asset_id"].nunique()),
        "cycles": int(len(replay_frame)),
        "kb": round(REPLAY.stat().st_size / 1024, 1),
    }
    log.info("replay artifact: %(units)d units, %(cycles)d cycles", summary)
    return summary


def _ingest() -> dict:
    adapters = {"cmapss": load_adapter("cmapss"), "ai4i": load_adapter("ai4i")}
    results = {}
    for name, adapter in adapters.items():
        raw = adapter.load()
        report = validate_dataset(raw, adapter.schema)
        if not report.ok:
            raise ValueError(
                f"{name} failed validation: "
                + "; ".join(issue.message for issue in report.errors)
            )
        cleaned = clean_frame(raw, adapter.schema)
        path = save_processed(cleaned.frame, adapter.info.name)
        quality = report.to_dict()
        quality["cleaning_notes"] = cleaned.notes
        _register_dataset(adapter, cleaned.frame, quality, path)
        results[name] = {
            "adapter": adapter,
            "raw": raw,
            "frame": cleaned.frame,
            "quality": quality,
            "path": path,
            "eda": build_eda(cleaned.frame, adapter.schema).payload,
        }
        log.info("%s: %d rows, quality %.1f/100", name, len(cleaned.frame), report.score)
    return results


def _drift_report(cmapss_raw: pd.DataFrame, ai4i: pd.DataFrame) -> dict:
    def entries(reference: pd.DataFrame, current: pd.DataFrame, columns: list[str], label: str):
        rows = []
        for column in columns:
            value = psi(reference[column], current[column])
            rows.append({
                "feature": column,
                "psi": round(value, 4),
                "status": psi_status(value),
            })
        rows.sort(key=lambda row: row["psi"], reverse=True)
        return {"comparison": label, "features": rows}

    ai4i_features = ["air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm",
                     "tool_wear_min"]
    split = len(ai4i) // 2
    ai4i_drift = entries(
        ai4i.iloc[:split], ai4i.iloc[split:], ai4i_features,
        "first half vs second half of the AI4I process sequence",
    )
    sensors = ["s2", "s3", "s4", "s7", "s8", "s11", "s12", "s15", "s17", "s20", "s21"]
    split_unit = int(cmapss_raw["asset_id"].median())
    cmapss_drift = entries(
        cmapss_raw[cmapss_raw["asset_id"] <= split_unit],
        cmapss_raw[cmapss_raw["asset_id"] > split_unit],
        sensors,
        f"C-MAPSS units <= {split_unit} vs units > {split_unit}",
    )
    worst = max([r["psi"] for r in ai4i_drift["features"] + cmapss_drift["features"]] or [0.0])
    return {
        "ai4i": ai4i_drift,
        "cmapss": cmapss_drift,
        "worst_psi": round(worst, 4),
        "overall_status": psi_status(worst),
        "method": "Population Stability Index over decile bins of the reference sample",
        "thresholds": {"stable": "< 0.10", "monitor": "0.10 - 0.25", "drift": ">= 0.25"},
        "note": (
            "C-MAPSS comparisons include genuine degradation and unit-to-unit variation; "
            "PSI flags distribution change, not necessarily a data-pipeline fault."
        ),
    }


def _ai4i_explanations(classifier_result, frame: pd.DataFrame) -> dict:
    featured, _ = build_tabular_features(frame)
    features = classifier_result.feature_names
    probabilities = classifier_result.fitted_model.predict_proba(featured[features])[:, 1]
    featured = featured.assign(_probability=probabilities)
    reference = featured[features].median()

    failed = featured[featured["machine_failure"] == 1].sort_values("_probability")
    healthy = featured[featured["machine_failure"] == 0].sort_values("_probability")
    picks = [
        ("Highest-risk recorded failure", failed.iloc[-1] if len(failed) else None),
        ("Median-risk recorded failure", failed.iloc[len(failed) // 2] if len(failed) else None),
        ("Lowest-risk healthy record", healthy.iloc[0] if len(healthy) else None),
    ]
    samples = []
    for title, row in picks:
        if row is None:
            continue
        explanation = occlusion_explanation(
            classifier_result.fitted_model.predict_proba,
            row[features], reference,
        )
        samples.append({
            "title": title,
            "row_id": int(row["row_id"]),
            "product_type": str(row["product_type"]),
            "actual_failure": int(row["machine_failure"]),
            "probability": round(explanation.probability, 4),
            "threshold": round(classifier_result.threshold, 4),
            "decision": "alert" if explanation.probability >= classifier_result.threshold else "pass",
            "contributions": [
                {"feature": c["feature"], "label": SENSOR_LABELS_AI4I.get(c["feature"], c["feature"]),
                 "value": round(c["value"], 3), "contribution": round(c["contribution"], 4)}
                for c in explanation.contributions
            ],
            "narrative": humanize_explanation(
                explanation.probability, explanation.contributions,
                lambda f: SENSOR_LABELS_AI4I.get(f, f),
            ),
        })
    return {
        "dataset": "ai4i",
        "global_importance": [
            {"feature": row["feature"], "label": SENSOR_LABELS_AI4I.get(row["feature"], row["feature"]),
             "importance": round(row["importance"], 4), "std": round(row["std"], 4)}
            for row in classifier_result.feature_importance
        ],
        "samples": samples,
        "method": (
            "Permutation importance (global) and occlusion attribution (local): each feature is "
            "replaced by the training median and the change in predicted probability is measured."
        ),
        "calibration": classifier_result.calibration,
        "failure_modes": classifier_result.failure_modes,
        "limitations": [
            "Attribution describes model behaviour, not proven physical causation.",
            "AI4I's power/overstrain/heat modes are deterministic functions of the recorded "
            "channels, so their near-perfect PR-AUC reflects label construction, not field realism.",
            "Occlusion attributions are not additive SHAP values; they are local sensitivity.",
        ],
    }


def build() -> dict:
    started = time.perf_counter()
    settings.ensure_dirs()
    init_db()
    _prune_registry()
    log.info("SENTINEL build started (%s)", BUILD_NAME)

    ingested = _ingest()
    cmapss_adapter = ingested["cmapss"]["adapter"]
    cmapss_frame = ingested["cmapss"]["frame"]
    ai4i_frame = ingested["ai4i"]["frame"]

    log.info("training RUL model")
    rul_result = train_rul_model(cmapss_adapter)

    log.info("building fleet features")
    sensor_columns = [c for c in cmapss_adapter.schema.sensor_columns if c in cmapss_frame.columns]
    feature_frame, specs = build_time_series_features(
        cmapss_frame, sensor_columns, group_col="asset_id", time_col="cycle"
    )
    feature_names = model_feature_columns(specs, feature_frame, extra=["op1", "op2", "op3"])

    log.info("fitting anomaly ensemble")
    anomaly_result = fit_anomaly_detectors(
        feature_frame, feature_names=feature_names, score_frame=rul_result.fleet_features
    )

    log.info("assembling fleet state")
    assets, fleet_frame = assemble_assets(
        feature_frame=rul_result.fleet_history,
        rul_predictions=rul_result.fleet_predictions,
        anomaly_frame=anomaly_result.frame,
        residuals=rul_result.residuals,
        anomaly_reference=anomaly_result.thresholds["high"],
        anomaly_baseline=anomaly_result.summary["healthy_score_median"],
    )
    replay_summary = _export_replay(fleet_frame)
    alerts = build_alerts(assets)
    with session_scope() as session:
        session.execute(delete(AlertRecord))
        for alert in alerts:
            session.add(AlertRecord(
                asset_id=alert["asset_id"], severity=alert["severity"], kind=alert["kind"],
                message=alert["message"], cycle=int(alert["cycle"]), score=float(alert["score"]),
            ))

    log.info("training failure classifier on AI4I")
    classifier_result = train_failure_classifier(ai4i_frame)
    explainability = _ai4i_explanations(classifier_result, ai4i_frame)

    log.info("training sensor forecast models")
    forecast_result = train_sensor_forecast(cmapss_frame)

    plan = build_plan(
        [
            {
                "asset_id": a["id"],
                "criticality": a["criticality"],
                "failure_risk": a["rul"]["horizon_risk"].get("30", 0.0),
                "predicted_rul": a["rul"]["estimate"],
            }
            for a in assets
        ],
        budget=settings.maintenance_budget,
    )
    maintenance = {
        "budget": plan.budget,
        "spent": plan.spent,
        "expected_avoided_loss": plan.expected_avoided_loss,
        "expected_downtime_hours": plan.expected_downtime_hours,
        "selected": plan.selected,
        "deferred": plan.deferred[:40],
        "scenarios": plan.scenarios,
        "assumptions": plan.assumptions,
        "notes": plan.notes,
        "health_weights": weights_payload(),
    }

    _register_model(
        "cmapss_rul", "rul_regression", "cmapss", rul_result.best_name,
        {"official_test": rul_result.official_test_metrics,
         "validation": rul_result.validation_metrics,
         "residual_quantiles": rul_result.residual_quantiles},
        {"clip": settings.rul_clip, "windows": list(settings.rolling_windows),
         "features": len(rul_result.feature_names)},
    )
    _register_model(
        "ai4i_failure_classifier", "failure_classification", "ai4i",
        classifier_result.best_name,
        {"test": classifier_result.test_metrics, "threshold": classifier_result.threshold,
         "calibration": classifier_result.calibration,
         "comparison": classifier_result.comparison},
        {"features": len(classifier_result.feature_names), "seed": settings.random_seed},
    )
    _register_model(
        "cmapss_sensor_forecast", "sensor_forecasting", "cmapss",
        forecast_result.payload["summary"]["best_model"],
        {"summary": forecast_result.payload["summary"],
         "best": forecast_result.payload["best"]},
        {"sensors": list(forecast_result.payload["sensors"]),
         "horizons": forecast_result.payload["all_horizons"],
         "train_fraction": forecast_result.payload["validation"]["train_fraction"]},
    )

    drift = _drift_report(cmapss_frame, ai4i_frame)
    meta = {
        "product": "SENTINEL",
        "build_version": BUILD_NAME,
        "package_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": "python -m sentinel.pipelines.build",
        "data_source": "artifact_snapshot",
        "duration_seconds": round(time.perf_counter() - started, 1),
        "dataset_versions": {
            name: {
                "version": frame_version(payload["frame"]),
                "rows": int(len(payload["frame"])),
                "quality_score": payload["quality"]["score"],
                "source_url": payload["adapter"].info.source_url,
            }
            for name, payload in ingested.items()
        },
        "feature_specs": len(specs),
        "runtime": {"python": platform.python_version(), "platform": platform.system()},
    }
    snapshot = sanitize(compose_snapshot(
        meta=meta,
        assets=assets,
        alerts=alerts,
        rul_result=rul_result,
        classifier_result=classifier_result,
        anomaly_result=anomaly_result,
        maintenance=maintenance,
        explainability=explainability,
        forecast=forecast_result.payload,
        drift=drift,
        models=list_models(),
        datasets=list_datasets(),
        eda={name: payload["eda"] for name, payload in ingested.items()},
    ))

    payload_text = json.dumps(snapshot, allow_nan=False, default=str)
    SNAPSHOT.write_text(payload_text, encoding="utf-8")
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "snapshot.json").write_text(payload_text, encoding="utf-8")
    log.info("snapshot written: %.0f KB", SNAPSHOT.stat().st_size / 1024)

    return {
        "assets": len(assets),
        "alerts": len(alerts),
        "replay": replay_summary,
        "rul": rul_result.official_test_metrics,
        "classifier": classifier_result.test_metrics,
        "duration_seconds": round(time.perf_counter() - started, 1),
        "snapshot_kb": round(SNAPSHOT.stat().st_size / 1024, 1),
    }


if __name__ == "__main__":
    summary = build()
    print(json.dumps(summary, indent=2, default=str))
