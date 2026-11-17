"""Partial-sensor health: per-asset baseline, signal thresholds and plant alerts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from sentinel.api.main import app
from sentinel.onboarding.health import (MIN_CYCLES_FOR_HEALTH, assess, build_baseline,
                                        insufficient_signal)
from sentinel.store.db import (AlertRecord, PlantAssetRecord, list_alerts, session_scope,
                               sync_alerts)

client = TestClient(app)
PREFIX = "PYTEST-HEALTH-"


def _csv(asset: str, cycles: int, sensors: int, spike: bool = False) -> tuple[str, dict]:
    headers = ["Engine ID", "Cycle"] + [f"Sensor_{i}" for i in range(1, sensors + 1)]
    rows = [",".join(headers)]
    for cycle in range(1, cycles + 1):
        values = [asset, str(cycle)]
        for index in range(1, sensors + 1):
            value = 10.0 + index + cycle * 0.1
            if spike and index == 1 and cycle > cycles - 4:
                value += 10.0
            values.append(f"{value:.3f}")
        rows.append(",".join(values))
    mapping = {"Engine ID": "asset_id", "Cycle": "cycle"}
    mapping.update({f"Sensor_{i}": f"s{i}" for i in range(1, sensors + 1)})
    return "\n".join(rows), mapping


def _cleanup() -> None:
    with session_scope() as session:
        rows = session.query(PlantAssetRecord).filter(
            PlantAssetRecord.asset_id.like(f"{PREFIX}%")
        ).all()
        paths = [Path(row.parquet_path) for row in rows if row.parquet_path]
        session.execute(delete(PlantAssetRecord).where(
            PlantAssetRecord.asset_id.like(f"{PREFIX}%")
        ))
        session.execute(delete(AlertRecord).where(AlertRecord.asset_id.like(f"{PREFIX}%")))
    for path in paths:
        path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def clean_registry():
    _cleanup()
    yield
    _cleanup()


def _import(asset: str, cycles: int, sensors: int, *, spike: bool = False,
            name: str | None = None) -> dict:
    text, mapping = _csv(asset, cycles, sensors, spike)
    response = client.post("/api/v1/onboarding/import", json={
        "name": name or f"Pytest {asset}", "csv_text": text, "mapping": mapping,
    })
    assert response.status_code == 200, response.text
    return response.json()["assets"][0]


def test_baseline_learns_normal_and_detects_a_shift():
    rng = np.random.default_rng(7)
    frame = pd.DataFrame([
        {"cycle": cycle, "s1": 10 + cycle * 0.05 + rng.normal(0, 0.3),
         "s2": 5 + rng.normal(0, 0.2), "s3": 20 + rng.normal(0, 0.4)}
        for cycle in range(1, 41)
    ])
    baseline = build_baseline(frame, ["s1", "s2", "s3"])
    assert baseline is not None and baseline["baseline_cycles"] == 12

    normal = assess(frame, baseline)
    assert normal["usable"] is True
    assert normal["health_score"] >= 80
    assert normal["category"] == "healthy"
    assert normal["coverage"]["confidence"] == "medium"

    shifted = frame.copy()
    for index in range(35, 40):
        shifted.loc[index, "s1"] += (index - 34) * 0.8
    degraded = assess(shifted, baseline)
    assert degraded["health_score"] < normal["health_score"]
    assert degraded["category"] in {"warning", "critical"}
    assert degraded["severity"] in {"high", "critical"}
    assert degraded["top_sensor"] == "s1"


def test_signal_thresholds_are_explicit():
    rng = np.random.default_rng(3)
    short = pd.DataFrame([{"cycle": cycle, "s1": 10 + rng.normal(0, 0.2)}
                          for cycle in range(1, MIN_CYCLES_FOR_HEALTH)])
    assert build_baseline(short, ["s1"]) is None
    unusable = insufficient_signal(short, ["s1"], 1)
    assert unusable["usable"] is False
    assert any("cycles" in reason for reason in unusable["reasons"])

    one_sensor = pd.DataFrame([{"cycle": cycle, "s1": 10 + rng.normal(0, 0.2)}
                               for cycle in range(1, 25)])
    baseline = build_baseline(one_sensor, ["s1"])
    signal = assess(one_sensor, baseline)
    assert signal["usable"] is True
    assert signal["coverage"]["confidence"] == "low"
    assert signal["coverage"]["recommended_sensors"] == 3


def test_partial_import_creates_health_and_plant_alert():
    asset = _import(f"{PREFIX}PARTIAL", cycles=26, sensors=3, spike=True)
    assert asset["score_eligible"] is False
    assert asset["baseline"] is not None
    assert asset["baseline_cycles"] >= MIN_CYCLES_FOR_HEALTH
    assert set(asset["baseline"]["sensors"]) == {"s1", "s2", "s3"}
    assert asset["health"]["usable"] is True
    assert asset["health"]["coverage"]["sensors"] == 3
    assert asset["health_score"] is not None and asset["health_score"] < 60
    assert asset["health_status"] in {"warning", "critical"}

    alerts = [row for row in list_alerts(limit=200, asset_id=asset["asset_id"])
              if row["kind"] == "plant_health"]
    assert len(alerts) == 1
    assert alerts[0]["source"] == "plant"
    assert alerts[0]["severity"] in {"high", "critical"}

    # C-MAPSS alert synchronisation must not touch plant alerts. The pipeline's
    # source-scoped prune is covered by the query filter; pruning here would
    # destroy unrelated developer alerts, so only the non-pruning path runs.
    sync_alerts([], prune=False)
    assert list_alerts(limit=200, asset_id=asset["asset_id"])

    refresh = client.post(f"/api/v1/onboarding/assets/{asset['id']}/health")
    assert refresh.status_code == 200
    assert refresh.json()["health"]["usable"] is True


def test_health_overview_reports_coverage_and_rul_stays_opt_in():
    partial = _import(f"{PREFIX}OVERVIEW", cycles=26, sensors=4)
    overview = client.get("/api/v1/onboarding/health").json()
    row = next(item for item in overview["assets"] if item["id"] == partial["id"])
    assert row["usable"] is True
    assert row["sensors"] == 4
    assert row["confidence"] == "medium"
    assert overview["minimum_signal"]["sensors"] == 1
    assert overview["minimum_signal"]["usable_sensors"] == 3
    assert overview["minimum_signal"]["rul_sensors"] == 21
    assert "3 sensors and 20 cycles" in overview["guidance"]
    assert overview["summary"]["with_signal"] >= 1

    blocked = client.post(f"/api/v1/onboarding/assets/{partial['id']}/score")
    assert blocked.status_code == 422
    assert "sensors" in blocked.json()["error"]["message"]


def test_one_sensor_and_short_history_are_reported_not_crashed():
    one = _import(f"{PREFIX}ONE", cycles=24, sensors=1)
    assert one["health"]["usable"] is True
    assert one["health"]["coverage"]["confidence"] == "low"

    short = _import(f"{PREFIX}SHORT", cycles=8, sensors=2)
    assert short["health"]["usable"] is False
    assert short["health"]["reasons"]
    assert short["health_score"] is None
