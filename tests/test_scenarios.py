"""Saved maintenance scenario tests: summaries, comparison and API round-trip."""

from __future__ import annotations

from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from sentinel.api.main import app
from sentinel.config import ARTIFACTS
from sentinel.decision.optimizer import build_plan
from sentinel.decision.scenarios import compare, summarize_plan
from sentinel.store.db import delete_scenario, get_scenario, list_scenarios, save_scenario

client = TestClient(app)
PREFIX = "pytest-scenario-"

ASSETS = [
    {"asset_id": "A", "criticality": 3, "failure_risk": 0.95, "predicted_rul": 8},
    {"asset_id": "B", "criticality": 2, "failure_risk": 0.75, "predicted_rul": 22},
    {"asset_id": "C", "criticality": 2, "failure_risk": 0.55, "predicted_rul": 45},
    {"asset_id": "D", "criticality": 1, "failure_risk": 0.35, "predicted_rul": 70},
    {"asset_id": "E", "criticality": 1, "failure_risk": 0.20, "predicted_rul": 90},
]


def _plans() -> tuple[dict, dict]:
    small = asdict(build_plan(ASSETS, budget=150))
    large = asdict(build_plan(ASSETS, budget=600))
    return small, large


def test_summary_exposes_comparison_fields():
    small, _ = _plans()
    summary = summarize_plan(small, scenario_id=1, name="Small budget")
    assert summary["budget"] == 150
    assert summary["assets_serviced"] == len(small["selected"])
    assert summary["selected_assets"] == [row["asset_id"] for row in small["selected"]]
    if small["spent"] > 0:
        assert summary["avoided_per_1000_spent"] is not None


def test_comparison_marks_best_value_per_metric():
    small, large = _plans()
    result = compare([
        summarize_plan(small, scenario_id=1, name="Small"),
        summarize_plan(large, scenario_id=2, name="Large"),
    ])
    metrics = {entry["key"]: entry for entry in result["metrics"]}

    assert "1" in metrics["spent"]["best_ids"], "the smaller budget must win on spend"
    assert "2" in metrics["expected_avoided_loss"]["best_ids"]
    assert metrics["expected_avoided_loss"]["better"] == "higher"
    assert metrics["expected_avoided_loss"]["values"]["2"] == pytest.approx(
        large["expected_avoided_loss"], abs=0.01
    )
    assert result["deltas_vs_first"]["2"]["expected_avoided_loss"] >= 0
    assert result["assets"]["shared_count"] <= min(
        len(small["selected"]), len(large["selected"])
    )
    assert "not measured" in result["note"]


def test_comparison_requires_two_scenarios():
    small, _ = _plans()
    with pytest.raises(ValueError):
        compare([summarize_plan(small, scenario_id=1, name="Only")])


def test_store_round_trip_and_delete():
    small, _ = _plans()
    saved = save_scenario(PREFIX + "store", small, note="unit test")
    try:
        fetched = get_scenario(saved["id"])
        assert fetched and fetched["plan"]["budget"] == 150
        assert any(row["id"] == saved["id"] for row in list_scenarios())
        assert delete_scenario(saved["id"]) is True
        assert get_scenario(saved["id"]) is None
    finally:
        delete_scenario(saved["id"])


@pytest.mark.skipif(
    not (ARTIFACTS / "snapshot.json").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)
def test_api_save_compare_and_delete():
    first = client.post("/api/v1/maintenance/scenarios",
                        json={"name": PREFIX + "api-small", "budget": 400})
    second = client.post("/api/v1/maintenance/scenarios",
                         json={"name": PREFIX + "api-large", "budget": 1600})
    assert first.status_code == 200 and second.status_code == 200
    small, large = first.json(), second.json()
    try:
        assert small["assets_serviced"] >= 0
        assert small["budget"] == 400 and large["budget"] == 1600

        listed = client.get("/api/v1/maintenance/scenarios").json()["scenarios"]
        assert {small["id"], large["id"]} <= {row["id"] for row in listed}

        compared = client.get(
            f"/api/v1/maintenance/scenarios/compare?ids={small['id']}&ids={large['id']}"
        )
        assert compared.status_code == 200
        payload = compared.json()
        assert [row["id"] for row in payload["scenarios"]] == [small["id"], large["id"]]
        assert len(payload["metrics"]) >= 5
        assert payload["deltas_vs_first"][str(large["id"])]

        single = client.get(f"/api/v1/maintenance/scenarios/{small['id']}")
        assert single.status_code == 200
        assert single.json()["plan"]["budget"] == 400
    finally:
        client.delete(f"/api/v1/maintenance/scenarios/{small['id']}")
        client.delete(f"/api/v1/maintenance/scenarios/{large['id']}")


@pytest.mark.skipif(
    not (ARTIFACTS / "snapshot.json").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)
def test_api_scenario_validation_and_unknown_ids():
    assert client.post("/api/v1/maintenance/scenarios",
                       json={"name": "", "budget": 500}).status_code == 422
    assert client.post("/api/v1/maintenance/scenarios",
                       json={"name": PREFIX + "bad", "budget": -5}).status_code == 422
    assert client.get("/api/v1/maintenance/scenarios/compare?ids=1").status_code == 422
    missing = client.get("/api/v1/maintenance/scenarios/compare?ids=999998&ids=999999")
    assert missing.status_code == 404
    assert client.get("/api/v1/maintenance/scenarios/999999").status_code == 404
    assert client.delete("/api/v1/maintenance/scenarios/999999").status_code == 404
