"""Digital-twin tests: transparent scoring plus the ingest auth contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentinel.api.main import app
from sentinel.config import ARTIFACTS
from sentinel.twins import twin as scoring

client = TestClient(app)

requires_artifacts = pytest.mark.skipif(
    not (ARTIFACTS / "snapshot.json").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)

SERIES = {
    "s2": [640.0 + index * 0.05 for index in range(40)],
    "s3": [1590.0 + index * 0.04 for index in range(40)],
    "s8": [48.0 - index * 0.01 for index in range(40)],
}


def healthy_sample() -> dict:
    baseline = scoring.build_baseline(SERIES, cycles=30)
    return {key: channel["median"] for key, channel in baseline["channels"].items()}


def test_baseline_uses_median_and_robust_scale():
    baseline = scoring.build_baseline(SERIES, cycles=30)
    assert baseline["sensor_count"] == 3
    assert baseline["channels"]["s2"]["samples"] == 30
    assert baseline["channels"]["s2"]["median"] == pytest.approx(640.725)
    assert baseline["channels"]["s2"]["scale"] > 0


def test_sample_at_the_baseline_scores_healthy():
    assessment = scoring.assess(healthy_sample(), scoring.build_baseline(SERIES))
    assert assessment["usable"] is True
    assert assessment["category"] == "healthy"
    assert assessment["health_score"] > 90
    assert assessment["coverage"]["coverage"] == 1.0
    assert assessment["severity"] == "normal"


def test_deviation_lowers_health_and_escalates_severity():
    baseline = scoring.build_baseline(SERIES)
    sample = healthy_sample()
    sample["s3"] = sample["s3"] + 12 * baseline["channels"]["s3"]["scale"]
    assessment = scoring.assess(sample, baseline)
    assert assessment["health_score"] < 60
    assert assessment["severity"] == "critical"
    assert assessment["top_sensors"][0]["sensor"] == "s3"


def test_partial_coverage_is_penalised_not_ignored():
    baseline = scoring.build_baseline(SERIES)
    sample = {"s2": baseline["channels"]["s2"]["median"]}
    assessment = scoring.assess(sample, baseline)
    assert assessment["coverage"]["matched"] == 1
    assert assessment["coverage"]["coverage"] == pytest.approx(1 / 3, rel=1e-3)
    assert assessment["health_score"] < 95
    assert set(assessment["coverage"]["missing"]) == {"s3", "s8"}


def test_unknown_channels_are_reported_not_scored():
    baseline = scoring.build_baseline(SERIES)
    sample = {**healthy_sample(), "s99": 1.0}
    assessment = scoring.assess(sample, baseline)
    assert "s99" in assessment["coverage"]["unknown"]
    assert assessment["coverage"]["matched"] == 3


def test_non_finite_values_are_rejected():
    baseline = scoring.build_baseline(SERIES)
    assessment = scoring.assess({"s2": float("nan")}, baseline)
    assert assessment["usable"] is False
    assert assessment["coverage"]["rejected"] == ["s2"]


def test_trend_reports_direction():
    history = [{"health": 95 - index} for index in range(8)]
    assert scoring.trend(history)["direction"] == "degrading"
    assert scoring.trend(history[:2])["direction"] == "unknown"


def test_security_headers_are_present():
    response = client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@requires_artifacts
def test_device_registration_and_ingest_require_the_token():
    assets = client.get("/api/v1/fleet/assets?sort=health").json()["assets"]
    asset_id = assets[0]["id"]
    created = client.post(
        "/api/v1/devices",
        json={"name": "Twin auth test", "asset_id": asset_id, "mode": "manual"},
    )
    assert created.status_code == 200
    body = created.json()
    device_id = body["device"]["device_id"]
    token = body["token"]
    assert token.startswith("sntl_")
    assert body["device"]["token_prefix"] == token[:12]

    try:
        assert client.get("/api/v1/devices").status_code == 200
        snapshot = client.get(f"/api/v1/devices/{device_id}").json()
        assert snapshot["baseline"]["sensor_count"] > 0
        sample = {
            key: channel["median"]
            for key, channel in snapshot["baseline"]["channels"].items()
        }

        anonymous = client.post(f"/api/v1/devices/{device_id}/telemetry",
                                json={"sensors": sample})
        assert anonymous.status_code == 401

        wrong = client.post(f"/api/v1/devices/{device_id}/telemetry",
                            json={"sensors": sample},
                            headers={"X-Device-Token": "sntl_not-the-token"})
        assert wrong.status_code == 401

        accepted = client.post(f"/api/v1/devices/{device_id}/telemetry",
                               json={"sensors": sample, "cycle": 7},
                               headers={"X-Device-Token": token})
        assert accepted.status_code == 200
        twin = accepted.json()["twin"]
        assert twin["category"] == "healthy"
        assert twin["coverage"]["matched"] == len(sample)

        after = client.get(f"/api/v1/devices/{device_id}").json()
        assert after["sample_count"] == 1
        assert after["latest"]["cycle"] == 7
        assert after["model"]["asset_id"] == asset_id

        rotated = client.post(f"/api/v1/devices/{device_id}/rotate-token").json()
        assert rotated["token"] != token
        stale = client.post(f"/api/v1/devices/{device_id}/telemetry",
                            json={"sensors": sample},
                            headers={"X-Device-Token": token})
        assert stale.status_code == 401
    finally:
        assert client.delete(f"/api/v1/devices/{device_id}").status_code == 200
    assert client.get(f"/api/v1/devices/{device_id}").status_code == 404


@requires_artifacts
def test_auto_mode_needs_a_bound_asset_and_can_start_and_stop():
    created = client.post("/api/v1/devices", json={"name": "Twin auto test"}).json()
    device_id = created["device"]["device_id"]
    try:
        blocked = client.post(f"/api/v1/devices/{device_id}/auto/start")
        assert blocked.status_code == 422
        assert "bind" in blocked.json()["error"]["message"].lower()

        assets = client.get("/api/v1/fleet/assets?sort=health").json()["assets"]
        patched = client.patch(f"/api/v1/devices/{device_id}",
                               json={"asset_id": assets[0]["id"], "mode": "auto",
                                     "interval_ms": 250})
        assert patched.status_code == 200
        started = client.post(f"/api/v1/devices/{device_id}/auto/start")
        assert started.status_code == 200
        assert started.json()["auto"]["running"] is True
        stopped = client.post(f"/api/v1/devices/{device_id}/auto/stop")
        assert stopped.status_code == 200
        assert stopped.json()["auto"]["running"] is False
    finally:
        client.delete(f"/api/v1/devices/{device_id}")
