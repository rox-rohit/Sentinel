"""Real-plant onboarding tests: mapping, validation gate, registry and scoring gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from sentinel.api.main import app
from sentinel.config import ARTIFACTS
from sentinel.onboarding.plant import suggest_target, validate_csv
from sentinel.store.db import PlantAssetRecord, get_plant_asset, session_scope

client = TestClient(app)
ASSET = "PYTEST-PLANT-001"


def _csv(cycles: int = 40, asset: str = ASSET, sensors: int = 21,
         bad_sensor: bool = False) -> tuple[str, dict[str, str]]:
    headers = ["Engine ID", "Cycle"] + [f"Sensor_{i}" for i in range(1, sensors + 1)]
    rows = [",".join(headers)]
    for cycle in range(1, cycles + 1):
        values = [asset, str(cycle)]
        for index in range(1, sensors + 1):
            if bad_sensor and index == 2 and cycle == 3:
                values.append("not-a-number")
            else:
                values.append(f"{index * 10 + cycle * 0.25:.3f}")
        rows.append(",".join(values))
    mapping = {"Engine ID": "asset_id", "Cycle": "cycle"}
    mapping.update({f"Sensor_{i}": f"s{i}" for i in range(1, sensors + 1)})
    return "\n".join(rows), mapping


def _cleanup() -> None:
    with session_scope() as session:
        rows = session.query(PlantAssetRecord).filter(
            PlantAssetRecord.asset_id.like("PYTEST-PLANT-%")
        ).all()
        paths = [Path(row.parquet_path) for row in rows if row.parquet_path]
        session.execute(delete(PlantAssetRecord).where(
            PlantAssetRecord.asset_id.like("PYTEST-PLANT-%")
        ))
    for path in paths:
        path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def clean_registry():
    _cleanup()
    yield
    _cleanup()


def test_mapping_suggestions_cover_common_plant_headers():
    assert suggest_target("Engine ID") == ("asset_id", 1.0)
    assert suggest_target("Unit Number")[0] == "asset_id"
    assert suggest_target("Cycle")[0] == "cycle"
    assert suggest_target("Sensor_3")[0] == "s3"
    assert suggest_target("sensor-11")[0] == "s11"
    assert suggest_target("T24")[0] == "s3"
    assert suggest_target("HPC outlet temperature")[0] is None


def test_inspection_suggests_mapping_and_flags_unmapped():
    text, _ = _csv(cycles=5)
    response = client.post("/api/v1/onboarding/inspect?filename=plant.csv",
                           content=text, headers={"Content-Type": "text/csv"})
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == 5
    assert body["suggested_mapping"]["Engine ID"] == "asset_id"
    assert body["suggested_mapping"]["Cycle"] == "cycle"
    assert body["suggested_mapping"]["Sensor_7"] == "s7"
    assert body["unmapped"] == []


def test_validation_blocks_missing_required_mapping():
    text, mapping = _csv(cycles=5)
    mapping.pop("Cycle")
    report = validate_csv(text, mapping)
    assert report["readiness"] == "blocked"
    assert any(issue["code"] == "missing_required" for issue in report["issues"])


def test_validation_blocks_duplicate_keys_and_non_numeric_values():
    text, mapping = _csv(cycles=5)
    lines = text.splitlines()
    lines[2] = lines[1]  # duplicate asset/cycle
    report = validate_csv("\n".join(lines), mapping)
    assert report["readiness"] == "blocked"
    assert any(issue["code"] == "duplicate_keys" for issue in report["issues"])

    bad_text, bad_mapping = _csv(cycles=10, bad_sensor=True)
    bad_report = validate_csv(bad_text, bad_mapping)
    codes = {issue["code"] for issue in bad_report["issues"]}
    assert "non_numeric" in codes


def test_short_history_is_registered_but_not_score_eligible():
    text, mapping = _csv(cycles=10)
    report = validate_csv(text, mapping)
    assert report["readiness"] == "warnings"
    assert report["scoring"]["eligible"] is False
    assert any(issue["code"] == "short_history" for issue in report["issues"])


def test_full_mapping_is_ready_and_eligible():
    text, mapping = _csv(cycles=40)
    report = validate_csv(text, mapping)
    assert report["readiness"] == "ready", report["issues"]
    assert report["scoring"]["eligible"] is True
    assert report["scoring"]["mapped_sensors"] == 21
    assert report["asset_count"] == 1


def test_import_registers_asset_with_mapping_and_refuses_blocked_data():
    text, mapping = _csv(cycles=40)
    response = client.post("/api/v1/onboarding/import", json={
        "name": "Pytest Plant", "csv_text": text, "mapping": mapping,
        "source_file": "pytest.csv",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report"]["readiness"] == "ready"
    asset = body["assets"][0]
    assert asset["asset_id"] == ASSET
    assert asset["status"] == "ready" and asset["score_eligible"] is True
    assert asset["mapping"]["Engine ID"] == "asset_id"
    assert Path(asset["parquet_path"]).exists()
    assert get_plant_asset(asset["id"])["sensors"] == [f"s{i}" for i in range(1, 22)]

    listed = client.get("/api/v1/onboarding/assets").json()
    assert any(row["id"] == asset["id"] for row in listed["assets"])

    broken, broken_mapping = _csv(cycles=5)
    broken_mapping.pop("Engine ID")
    refused = client.post("/api/v1/onboarding/import", json={
        "name": "Broken", "csv_text": broken, "mapping": broken_mapping,
    })
    assert refused.status_code == 422


def test_import_short_history_then_scoring_gate_rejects():
    text, mapping = _csv(cycles=12)
    imported = client.post("/api/v1/onboarding/import", json={
        "name": "Pytest Short", "csv_text": text, "mapping": mapping,
    }).json()
    asset = imported["assets"][0]
    assert asset["status"] == "registered"
    rejected = client.post(f"/api/v1/onboarding/assets/{asset['id']}/score")
    assert rejected.status_code == 422
    assert "cycles" in rejected.json()["error"]["message"]


@pytest.mark.skipif(
    not (ARTIFACTS / "snapshot.json").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)
def test_ready_asset_scores_after_validation():
    text, mapping = _csv(cycles=40)
    imported = client.post("/api/v1/onboarding/import", json={
        "name": "Pytest Score", "csv_text": text, "mapping": mapping,
    }).json()
    asset = imported["assets"][0]
    scored = client.post(f"/api/v1/onboarding/assets/{asset['id']}/score")
    assert scored.status_code == 200, scored.text
    body = scored.json()
    assert body["eligible"] is True
    assert 0 <= body["prediction"]["predicted_rul"] <= body["prediction"]["clip"]
    assert "out-of-distribution" in body["warning"]


def test_unknown_asset_is_404():
    assert client.get("/api/v1/onboarding/assets/999999").status_code == 404
    assert client.post("/api/v1/onboarding/assets/999999/score").status_code == 404
