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
from sentinel.onboarding.plant import (MAX_CYCLES_FOR_SCORING, SENSORS, canonical_frame,
                                       parse_csv, validate_csv)
from sentinel.store.db import (get_mapping_profile, get_plant_asset, list_plant_assets,
                               touch_mapping_profile, upsert_plant_asset)

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
            "notes": notes,
        }))
    if profile_id is not None and drift is not None:
        touch_mapping_profile(
            profile_id,
            mapping=mapping if (accept_drift and drift["changed"]) else None,
            expected_columns=([str(column) for column in parse_csv(text).columns]
                              if (accept_drift and drift["changed"]) else None),
        )

    return {"report": report, "assets": registered, "stored_at": str(PLANT_DIR),
            "drift": drift}


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


__all__ = ["DriftBlocked", "OnboardingBlocked", "import_csv", "list_plant_assets",
           "resolve_profile", "score_asset"]
