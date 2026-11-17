"""Mapping profiles and schema-drift tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from sentinel.api.main import app
from sentinel.onboarding.drift import compare_columns
from sentinel.store.db import (MappingProfileRecord, PlantAssetRecord, get_mapping_profile,
                               session_scope)

client = TestClient(app)
PREFIX = "pytest-profile-"
ASSET = "PYTEST-DRIFT-ASSET"


def _headers() -> list[str]:
    return ["Engine ID", "Cycle"] + [f"Sensor_{i}" for i in range(1, 4)]


def _mapping() -> dict[str, str]:
    mapping = {"Engine ID": "asset_id", "Cycle": "cycle"}
    mapping.update({f"Sensor_{i}": f"s{i}" for i in range(1, 4)})
    return mapping


def _csv(columns: list[str] | None = None, cycles: int = 35,
         asset: str = ASSET) -> str:
    columns = columns or _headers()
    rows = [",".join(columns)]
    for cycle in range(1, cycles + 1):
        values = []
        for column in columns:
            if "Sensor" in column or "sensor" in column:
                values.append(f"{cycle * 1.5 + 10:.2f}")
            elif "Site" in column:
                values.append("Plant-A")
            elif column in {"Engine ID", "Engine_ID"}:
                values.append(asset)
            elif column == "Cycle":
                values.append(str(cycle))
            else:
                values.append("")
        rows.append(",".join(values))
    return "\n".join(rows)


def _cleanup() -> None:
    paths: list[Path] = []
    with session_scope() as session:
        profiles = session.query(MappingProfileRecord).filter(
            MappingProfileRecord.name.like(f"{PREFIX}%")
        ).all()
        for profile in profiles:
            session.delete(profile)
        assets = session.query(PlantAssetRecord).filter(
            PlantAssetRecord.asset_id.like("PYTEST-DRIFT-%")
        ).all()
        paths = [Path(asset.parquet_path) for asset in assets if asset.parquet_path]
        session.execute(delete(PlantAssetRecord).where(
            PlantAssetRecord.asset_id.like("PYTEST-DRIFT-%")
        ))
    for path in paths:
        path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def clean():
    _cleanup()
    yield
    _cleanup()


def _save_profile(name: str = PREFIX + "vendor-a") -> dict:
    return client.post("/api/v1/onboarding/profiles", json={
        "name": name,
        "source": "Vendor A historian",
        "mapping": _mapping(),
        "expected_columns": _headers(),
        "notes": "monthly export",
    }).json()


def test_unchanged_schema_reports_no_drift():
    drift = compare_columns(_headers(), _headers(), _mapping())
    assert drift["status"] == "unchanged"
    assert drift["changed"] is False
    assert drift["blocking"] is False
    assert drift["mapping"] == _mapping()


def test_added_column_is_reported_with_suggestion():
    drift = compare_columns(_headers(), _headers() + ["Site"], _mapping())
    assert drift["status"] == "drift" and drift["blocking"] is False
    assert drift["added"] == ["Site"]
    assert drift["mapping"] == _mapping()
    assert drift["requires_acknowledgement"] is True


def test_renamed_column_carries_the_mapping():
    current = ["Engine_ID", "Cycle"] + [f"Sensor_{i}" for i in range(1, 4)]
    drift = compare_columns(_headers(), current, _mapping())
    assert drift["blocking"] is True  # renames require acknowledgement
    assert drift["requires_acknowledgement"] is True
    assert len(drift["renamed"]) == 1
    assert drift["renamed"][0]["from"] == "Engine ID"
    assert drift["renamed"][0]["to"] == "Engine_ID"
    assert drift["mapping"]["Engine_ID"] == "asset_id"
    assert "Engine ID" not in drift["mapping"]


def test_missing_mapped_column_is_blocking_and_drops_target():
    current = ["Engine ID", "Cycle", "Sensor_2", "Sensor_3"]  # Sensor_1 removed
    drift = compare_columns(_headers(), current, _mapping())
    assert drift["blocking"] is True
    assert drift["missing"] == ["Sensor_1"]
    assert "s1" in drift["dropped_targets"]
    assert "Sensor_1" not in drift["mapping"]


def test_profile_crud_and_duplicate_names():
    created = _save_profile()
    assert created["id"] and created["use_count"] == 0
    assert created["mapping"]["Engine ID"] == "asset_id"

    duplicate = client.post("/api/v1/onboarding/profiles", json={
        "name": PREFIX + "vendor-a", "mapping": _mapping(), "expected_columns": _headers(),
    })
    assert duplicate.status_code == 409

    listed = client.get("/api/v1/onboarding/profiles").json()["profiles"]
    assert any(row["id"] == created["id"] for row in listed)

    updated = client.put(f"/api/v1/onboarding/profiles/{created['id']}", json={
        "name": PREFIX + "vendor-a-renamed",
        "source": "Vendor A v2",
        "mapping": _mapping(),
        "expected_columns": _headers(),
        "notes": "updated",
    })
    assert updated.status_code == 200
    assert updated.json()["source"] == "Vendor A v2"

    assert client.get(f"/api/v1/onboarding/profiles/{created['id']}").status_code == 200
    assert client.delete(f"/api/v1/onboarding/profiles/{created['id']}").status_code == 200
    assert client.get(f"/api/v1/onboarding/profiles/{created['id']}").status_code == 404


def test_apply_profile_detects_renamed_and_added_columns():
    profile = _save_profile()
    renamed = _csv(["Engine_ID", "Cycle", "Sensor_1", "Sensor_2", "Sensor_3", "Site"])
    response = client.post(f"/api/v1/onboarding/profiles/{profile['id']}/apply",
                           content=renamed)
    assert response.status_code == 200
    body = response.json()
    assert body["drift"]["status"] == "drift"
    assert body["drift"]["renamed"][0]["to"] == "Engine_ID"
    assert body["drift"]["added"] == ["Site"]
    assert body["mapping"]["Engine_ID"] == "asset_id"

    missing = client.post(f"/api/v1/onboarding/profiles/{profile['id']}/apply",
                          content=_csv(["Engine ID", "Cycle", "Sensor_2", "Sensor_3"]))
    assert missing.json()["drift"]["blocking"] is True


def test_validate_with_profile_includes_drift():
    profile = _save_profile()
    response = client.post("/api/v1/onboarding/validate", json={
        "csv_text": _csv(["Engine_ID", "Cycle", "Sensor_1", "Sensor_2", "Sensor_3"]),
        "profile_id": profile["id"],
        "source_file": "drifted.csv",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["drift"]["renamed"][0]["from"] == "Engine ID"
    assert body["readiness"] != "blocked", body["issues"]
    assert body["mapping"]["Engine_ID"] == "asset_id"


def test_import_requires_acknowledgement_then_refreshes_profile():
    profile = _save_profile()
    renamed = _csv(["Engine_ID", "Cycle", "Sensor_1", "Sensor_2", "Sensor_3"])

    refused = client.post("/api/v1/onboarding/import", json={
        "name": "Drift import", "csv_text": renamed, "profile_id": profile["id"],
    })
    assert refused.status_code == 409
    assert "renamed" in refused.json()["error"]["message"]

    accepted_rename = client.post("/api/v1/onboarding/import", json={
        "name": "Drift import", "csv_text": renamed, "profile_id": profile["id"],
        "accept_drift": True,
    })
    assert accepted_rename.status_code == 200, accepted_rename.text
    assert accepted_rename.json()["drift"]["renamed"][0]["to"] == "Engine_ID"

    refreshed = get_mapping_profile(profile["id"])
    assert refreshed["use_count"] == 1
    assert refreshed["mapping"]["Engine_ID"] == "asset_id"
    assert "Engine ID" not in refreshed["expected_columns"]

    blocked_text = _csv(["Engine_ID", "Cycle", "Sensor_2", "Sensor_3"])
    blocked = client.post("/api/v1/onboarding/import", json={
        "name": "Drift blocked", "csv_text": blocked_text, "profile_id": profile["id"],
    })
    assert blocked.status_code == 409
    assert "absent" in blocked.json()["error"]["message"]

    accepted = client.post("/api/v1/onboarding/import", json={
        "name": "Drift accepted", "csv_text": blocked_text, "profile_id": profile["id"],
        "accept_drift": True,
    })
    assert accepted.status_code == 200, accepted.text
    assert "Sensor_1" not in accepted.json()["report"]["mapping"]

    refreshed = get_mapping_profile(profile["id"])
    assert refreshed["use_count"] == 2
    assert "Sensor_1" not in refreshed["mapping"]


def test_unknown_profile_returns_404():
    assert client.get("/api/v1/onboarding/profiles/999999").status_code == 404
    response = client.post("/api/v1/onboarding/validate", json={
        "csv_text": _csv(), "profile_id": 999999,
    })
    assert response.status_code == 404
