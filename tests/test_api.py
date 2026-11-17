"""API integration tests against the built artifacts.

These require `python -m sentinel.pipelines.build` to have run (the snapshot and
model artifacts are build outputs, not repository files).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentinel.api.main import app
from sentinel.config import ARTIFACTS

pytestmark = pytest.mark.skipif(
    not (ARTIFACTS / "snapshot.json").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)

client = TestClient(app)


def test_health_and_status():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["artifacts_ready"] is True


def test_fleet_and_asset_contract():
    summary = client.get("/api/v1/fleet/summary")
    assert summary.status_code == 200
    assert summary.json()["summary"]["total"] > 0

    assets = client.get("/api/v1/fleet/assets?sort=risk").json()["assets"]
    assert assets and "health_score" in assets[0] and "rul" in assets[0]

    asset = client.get(f"/api/v1/fleet/assets/{assets[0]['id']}")
    assert asset.status_code == 200
    assert len(asset.json()["series"]["cycle"]) > 0


def test_unknown_asset_uses_the_error_envelope():
    response = client.get("/api/v1/fleet/assets/DOES-NOT-EXIST")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "http_404"
    assert payload["error"]["message"]


def test_failure_prediction_and_explanation_are_model_backed():
    payload = {
        "air_temp_k": 302.5,
        "process_temp_k": 312.0,
        "rotational_speed_rpm": 1300,
        "torque_nm": 65.0,
        "tool_wear_min": 220,
        "product_type": "L",
    }
    prediction = client.post("/api/v1/predict/failure", json=payload)
    assert prediction.status_code == 200
    body = prediction.json()
    assert 0.0 <= body["probability"] <= 1.0
    assert isinstance(body["alert"], bool)
    assert body["model"]

    explanation = client.post("/api/v1/predict/failure/explain", json=payload)
    assert explanation.status_code == 200
    explained = explanation.json()
    assert explained["contributions"]
    assert explained["method"]
    assert abs(explained["probability"] - body["probability"]) < 1e-6


def test_prediction_validation_rejects_impossible_values():
    response = client.post("/api/v1/predict/failure", json={"air_temp_k": -50})
    assert response.status_code == 422


def test_maintenance_optimisation_respects_budget():
    response = client.post("/api/v1/maintenance/optimize", json={"budget": 600})
    assert response.status_code == 200
    plan = response.json()
    assert plan["spent"] <= 600
    assert plan["budget"] == 600
    assert len(plan["scenarios"]) == 3


def test_catalog_routes_expose_build_artifacts():
    datasets = client.get("/api/v1/datasets").json()["datasets"]
    assert any(entry["name"] == "cmapss" for entry in datasets)
    models = client.get("/api/v1/models").json()["models"]
    assert any(entry["task"] == "rul_regression" for entry in models)
    assert client.get("/api/v1/eda?dataset=ai4i").status_code == 200
    assert client.get("/api/v1/drift").status_code == 200


def test_rul_prediction_from_sequence():
    readings = [
        {"cycle": cycle, **{f"s{i}": 40.0 + i * 0.2 + cycle * 0.01 for i in range(1, 22)}}
        for cycle in range(1, 41)
    ]
    response = client.post("/api/v1/predict/rul", json={"readings": readings})
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["predicted_rul"] <= body["clip"]
    assert body["lower"] <= body["predicted_rul"] + 1e-6


def test_rul_sequence_requires_enough_history():
    response = client.post(
        "/api/v1/predict/rul",
        json={"readings": [{"cycle": 1, **{f"s{i}": 1.0 for i in range(1, 22)}}]},
    )
    assert response.status_code == 422


def test_forecast_route_exposes_chronological_results():
    response = client.get("/api/v1/forecast")
    assert response.status_code == 200
    body = response.json()
    assert body["comparison"]
    assert body["best"]
    assert body["validation"]["protocol"]
    assert body["summary"]["best_model"]
