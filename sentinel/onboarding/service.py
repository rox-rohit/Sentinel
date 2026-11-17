"""Onboarding orchestration: validate, persist per-asset parquet, gate scoring.

Validation runs before anything is written or scored. Blocking errors refuse the
import; warnings allow registration but mark the asset as not score-eligible.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from sentinel.config import DATA_PROCESSED
from sentinel.inference.service import SentinelService
from sentinel.onboarding.drift import compare_columns
from sentinel.onboarding.health import (MIN_CYCLES_FOR_HEALTH, MIN_SENSORS_FOR_SIGNAL,
                                        RECOMMENDED_CYCLES, RECOMMENDED_SENSORS,
                                        assess, build_baseline, health_thresholds,
                                        insufficient_signal)
from sentinel.onboarding.plant import (MAX_CYCLES_FOR_SCORING, SENSORS, canonical_frame,
                                       parse_csv, validate_csv)
from sentinel.store.db import (get_mapping_profile, get_plant_asset, list_plant_assets,
                               touch_mapping_profile, update_plant_health, upsert_plant_alert,
                               upsert_plant_asset)

PLANT_DIR = DATA_PROCESSED / "plant"


class DriftBlocked(ValueError):
    """Raised when a saved profile's schema drifted and was not acknowledged."""

    def __init__(self, drift: dict) -> None:
        self.drift = drift
        super().__init__(drift.get("reason") or "Schema drift requires acknowledgement.")


class OnboardingBlocked(ValueError):
    """Raised when validation has blocking errors and the import is refused."""

    def __init__(self, report: dict) -> None:
        self.report = report
        errors = [issue for issue in report.get("issues", []) if issue["severity"] == "error"]
        super().__init__(
            f"Import blocked by {len(errors)} validation error(s): "
            + "; ".join(issue["message"] for issue in errors[:3])
        )


def resolve_profile(profile_id: int, text: str) -> tuple[dict, dict | None]:
    """Load a profile and compare its expected schema with the incoming file."""
    profile = get_mapping_profile(profile_id)
    if profile is None:
        raise LookupError(profile_id)
    frame = parse_csv(text)
    drift = compare_columns(profile["expected_columns"], [str(column) for column in frame.columns],
                            profile["mapping"])
    drift["profile_id"] = profile_id
    drift["profile_name"] = profile["name"]
    mapping = drift["mapping"] if drift["changed"] else profile["mapping"]
    return mapping, drift


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-") or "asset"


def import_csv(*, name: str, text: str, mapping: dict[str, str],
               source_file: str = "upload", notes: str | None = None,
               profile_id: int | None = None, accept_drift: bool = False) -> dict:
    drift = None
    if profile_id is not None:
        mapping, drift = resolve_profile(profile_id, text)
        if drift and drift["blocking"] and not accept_drift:
            raise DriftBlocked(drift)
    report = validate_csv(text, mapping, source_file=source_file)
    if drift is not None:
        report["drift"] = drift
    if report["readiness"] == "blocked":
        raise OnboardingBlocked(report)
    if not report["rows"]:
        raise OnboardingBlocked(report)

    canonical = canonical_frame(text, mapping)
    PLANT_DIR.mkdir(parents=True, exist_ok=True)
    mapped_sensors = [sensor for sensor in SENSORS if sensor in canonical.columns]
    registered = []
    for raw_asset_id, group in canonical.groupby("asset_id", sort=True):
        asset_id = str(raw_asset_id)
        asset_report = validate_csv(text, mapping, source_file=source_file)
        asset_issues = list(asset_report["issues"])
        rows = int(len(group))
        if rows < MAX_CYCLES_FOR_SCORING:
            asset_issues.append({
                "severity": "warning", "code": "short_history",
                "message": f"{asset_id} has {rows} cycles; at least "
                           f"{MAX_CYCLES_FOR_SCORING} are required for scoring.",
                "column": "cycle", "count": rows, "pct": 0.0,
            })
        eligible = bool(
            not any(issue["severity"] == "error" for issue in asset_issues)
            and len(mapped_sensors) == len(SENSORS)
            and rows >= MAX_CYCLES_FOR_SCORING
        )
        status = "ready" if eligible else "registered"
        filename = f"{_slug(name)}-{_slug(asset_id)}.parquet"
        path = PLANT_DIR / filename
        group.to_parquet(path, index=False)

        baseline = build_baseline(group, mapped_sensors)
        health = (assess(group, baseline) if baseline is not None
                  else insufficient_signal(group, mapped_sensors, len(mapped_sensors)))

        simplified = {
            "readiness": asset_report["readiness"],
            "quality_score": asset_report["quality_score"],
            "rows": rows,
            "asset_count": 1,
            "issues": asset_report["issues"],
            "error_count": asset_report["error_count"],
            "warning_count": asset_report["warning_count"],
            "scoring": {
                **asset_report["scoring"],
                "eligible": eligible,
                "min_cycles_required": MAX_CYCLES_FOR_SCORING,
            },
            "schema_version": asset_report["schema_version"],
            "source_file": source_file,
        }
        registered.append(upsert_plant_asset({
            "asset_id": asset_id,
            "name": f"{name} · {asset_id}" if report["asset_count"] > 1 else name,
            "source_file": source_file,
            "status": status,
            "score_eligible": eligible,
            "rows": rows,
            "cycles": rows,
            "min_cycle": int(group["cycle"].min()),
            "max_cycle": int(group["cycle"].max()),
            "sensors": mapped_sensors,
            "mapping": report["mapping"],
            "quality": simplified,
            "parquet_path": str(path),
            "baseline": baseline,
            "health": health,
            "notes": notes,
        }))
        _raise_plant_alert(registered[-1])
    if profile_id is not None and drift is not None:
        touch_mapping_profile(
            profile_id,
            mapping=mapping if (accept_drift and drift["changed"]) else None,
            expected_columns=([str(column) for column in parse_csv(text).columns]
                              if (accept_drift and drift["changed"]) else None),
        )

    return {"report": report, "assets": registered, "stored_at": str(PLANT_DIR),
            "drift": drift}


def _raise_plant_alert(asset: dict) -> None:
    """Feed usable partial-sensor health into the alert inbox."""
    health = asset.get("health") or {}
    if not health.get("usable"):
        return
    severity = health.get("severity", "normal")
    category = health.get("category", "healthy")
    if severity not in {"high", "critical"} and category not in {"warning", "critical"}:
        return
    alert_severity = (
        "critical" if severity == "critical" or category == "critical"
        else "high" if severity == "high" or category == "warning"
        else "medium"
    )
    coverage = health.get("coverage", {})
    upsert_plant_alert({
        "asset_id": asset["asset_id"],
        "label": asset["name"],
        "kind": "plant_health",
        "severity": alert_severity,
        "cycle": health.get("cycle", asset.get("max_cycle", 0)),
        "score": health.get("health_score", 0.0),
        "message": (
            f"Health {health['health_score']:.1f}/100 ({category}) from "
            f"{coverage.get('sensors', 0)} mapped sensor(s); anomaly "
            f"{health.get('anomaly_score', 0):.2f} sigma on {health.get('top_sensor', 'n/a')}. "
            f"Baseline {coverage.get('baseline_cycles', 0)} cycles, "
            f"{coverage.get('confidence', 'low')} confidence."
        ),
    })


def recompute_health(registry_id: int) -> dict:
    """Re-assess a registered asset from its stored parquet and baseline."""
    record = get_plant_asset(registry_id)
    if record is None:
        return {"found": False}
    path = Path(record["parquet_path"])
    if not path.exists():
        return {"found": True, "asset": record, "usable": False,
                "reasons": ["Stored parquet is missing; re-import the asset."]}
    frame = pd.read_parquet(path)
    mapped = [sensor for sensor in record["sensors"] if sensor in frame.columns]
    baseline = record.get("baseline")
    if not baseline:
        baseline = build_baseline(frame, mapped)
    health = (assess(frame, baseline) if baseline is not None
              else insufficient_signal(frame, mapped, len(mapped)))
    asset = update_plant_health(registry_id, baseline=baseline, health=health)
    if asset and health.get("usable"):
        _raise_plant_alert(asset)
    return {"found": True, "asset": asset, "health": health}


def health_overview() -> dict:
    """Fleet view of onboarded assets; never mixed with the C-MAPSS fleet."""
    assets = list_plant_assets(limit=500)
    rows = []
    counts = {"healthy": 0, "attention": 0, "warning": 0, "critical": 0}
    for asset in assets:
        health = asset.get("health") or {}
        usable = bool(health.get("usable"))
        category = health.get("category")
        if usable and category in counts:
            counts[category] += 1
        rows.append({
            "id": asset["id"],
            "asset_id": asset["asset_id"],
            "name": asset["name"],
            "cycles": asset["cycles"],
            "sensors": len(asset.get("sensors", [])),
            "baseline_cycles": asset.get("baseline_cycles", 0),
            "health_score": asset.get("health_score"),
            "health_status": asset.get("health_status"),
            "anomaly_score": asset.get("anomaly_score"),
            "severity": asset.get("severity"),
            "confidence": (health.get("coverage") or {}).get("confidence"),
            "usable": usable,
            "reasons": health.get("reasons", []),
            "score_eligible": asset["score_eligible"],
        })
    return {
        "assets": rows,
        "summary": {
            "total": len(rows),
            "with_signal": sum(1 for row in rows if row["usable"]),
            "without_signal": sum(1 for row in rows if not row["usable"]),
            "rul_eligible": sum(1 for row in rows if row["score_eligible"]),
            **counts,
        },
        "thresholds": health_thresholds(),
        "minimum_signal": {
            "sensors": MIN_SENSORS_FOR_SIGNAL,
            "cycles": MIN_CYCLES_FOR_HEALTH,
            "usable_sensors": RECOMMENDED_SENSORS,
            "usable_cycles": RECOMMENDED_CYCLES,
            "high_confidence_sensors": health_thresholds()["high_confidence_sensors"],
            "rul_sensors": len(SENSORS),
            "rul_cycles": MAX_CYCLES_FOR_SCORING,
        },
        "guidance": (
            f"{MIN_SENSORS_FOR_SIGNAL} mapped sensor and {MIN_CYCLES_FOR_HEALTH} cycles produce "
            f"a relative signal; {RECOMMENDED_SENSORS} sensors and {RECOMMENDED_CYCLES} cycles "
            "are the recommended minimum for a usable health signal. Full RUL still needs "
            f"all {len(SENSORS)} sensors and {MAX_CYCLES_FOR_SCORING} cycles."
        ),
        "limitations": [
            "Health is relative to each asset's own early-cycle baseline, not a fleet normal.",
            "Partial-sensor health cannot estimate remaining useful life.",
            "Fewer channels and a short baseline lower confidence; a baseline taken during "
            "a fault will mask that fault.",
            "The full 21-sensor RUL score remains an explicit opt-in and an out-of-distribution "
            "check for plant data.",
        ],
    }


def score_asset(registry_id: int, service: SentinelService) -> dict:
    record = get_plant_asset(registry_id)
    if record is None:
        return {"found": False}
    reasons: list[str] = []
    missing = [sensor for sensor in SENSORS if sensor not in record["sensors"]]
    if missing:
        reasons.append(f"{len(missing)} of 21 sensors are not mapped: {missing[:6]}")
    if record["cycles"] < MAX_CYCLES_FOR_SCORING:
        reasons.append(
            f"{record['cycles']} cycles recorded; {MAX_CYCLES_FOR_SCORING} required "
            "for the rolling feature windows."
        )
    if record["status"] != "ready" or not record["score_eligible"]:
        reasons.append(f"Registry status is {record['status']!r}.")
    if reasons:
        return {"found": True, "asset": record, "eligible": False, "reasons": reasons}

    path = Path(record["parquet_path"])
    if not path.exists():
        return {"found": True, "asset": record, "eligible": False,
                "reasons": ["Stored parquet is missing; re-import the asset."]}
    frame = pd.read_parquet(path)
    for column, default in (("op1", 0.0), ("op2", 0.0), ("op3", 0.0)):
        if column not in frame.columns:
            frame[column] = default
    readings = frame[["cycle", *SENSORS, "op1", "op2", "op3"]].to_dict(orient="records")
    prediction = service.predict_rul(readings)
    return {
        "found": True,
        "eligible": True,
        "asset": record,
        "prediction": prediction,
        "warning": (
            "The RUL model was trained on NASA C-MAPSS FD001 simulated engines. Applying it "
            "to plant telemetry is an out-of-distribution check, not a validated prediction; "
            "sensor units and operating conditions must match the training definition."
        ),
    }


__all__ = ["DriftBlocked", "OnboardingBlocked", "health_overview", "import_csv",
           "list_plant_assets", "recompute_health", "resolve_profile", "score_asset"]
