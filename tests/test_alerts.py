"""Alert lifecycle tests: stable identity, persistence and API transitions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from sentinel.api.main import app
from sentinel.config import ARTIFACTS
from sentinel.store.db import (AlertRecord, acknowledge_alert, alert_fingerprint, list_alerts,
                               resolve_alert, session_scope, sync_alerts)

TEST_ASSET = "TEST-ALERT-UNIT"
client = TestClient(app)


def _seed(cycle: int = 7, severity: str = "high") -> dict:
    sync_alerts(
        [{
            "asset_id": TEST_ASSET,
            "label": "Unit T",
            "kind": "anomaly",
            "severity": severity,
            "message": "Synthetic alert for lifecycle tests.",
            "cycle": cycle,
            "score": 1.25,
        }],
        prune=False,
    )
    rows = list_alerts(500, asset_id=TEST_ASSET)
    assert rows, "seeded alert should be readable"
    return rows[0]


def _cleanup() -> None:
    with session_scope() as session:
        session.execute(delete(AlertRecord).where(AlertRecord.asset_id == TEST_ASSET))


@pytest.fixture()
def alert():
    _cleanup()
    record = _seed()
    yield record
    _cleanup()


def test_fingerprint_is_stable_and_distinguishes_alerts():
    first = alert_fingerprint(TEST_ASSET, "anomaly", 7)
    assert first == alert_fingerprint(TEST_ASSET, "anomaly", 7)
    assert first != alert_fingerprint(TEST_ASSET, "anomaly", 8)
    assert first != alert_fingerprint(TEST_ASSET, "failure_risk", 7)
    assert first != alert_fingerprint("OTHER-UNIT", "anomaly", 7)


def test_acknowledgement_survives_a_rebuild_sync(alert):
    acknowledged = acknowledge_alert(alert["id"], actor="tester", note="inspected")
    assert acknowledged["status"] == "acknowledged"
    assert acknowledged["acknowledged_by"] == "tester"
    assert acknowledged["acknowledged_at"]

    # A rebuild refreshes severity/message but must keep the lifecycle state.
    _seed(cycle=7, severity="critical")
    after = list_alerts(500, asset_id=TEST_ASSET)[0]
    assert after["id"] == alert["id"]
    assert after["status"] == "acknowledged"
    assert after["acknowledged_by"] == "tester"
    assert after["severity"] == "critical"


def test_resolution_is_terminal(alert):
    resolved = resolve_alert(alert["id"], actor="tester")
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] and resolved["resolved_by"] == "tester"

    with pytest.raises(ValueError):
        resolve_alert(alert["id"], actor="tester")
    with pytest.raises(ValueError):
        acknowledge_alert(alert["id"], actor="tester")


def test_non_pruning_sync_keeps_unrelated_open_alerts(alert):
    sync_alerts([], prune=False)
    assert list_alerts(500, asset_id=TEST_ASSET)


def test_api_acknowledge_and_resolve(alert):
    ack = client.post(f"/api/v1/alerts/{alert['id']}/acknowledge",
                      json={"actor": "api-test", "note": "triaged"})
    assert ack.status_code == 200
    body = ack.json()
    assert body["status"] == "acknowledged" and body["acknowledged_by"] == "api-test"

    resolved = client.post(f"/api/v1/alerts/{alert['id']}/resolve", json={"actor": "api-test"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    again = client.post(f"/api/v1/alerts/{alert['id']}/resolve", json={"actor": "api-test"})
    assert again.status_code == 409
    assert again.json()["error"]["message"]


def test_api_rejects_unknown_alert_and_missing_actor():
    assert client.post("/api/v1/alerts/999999/acknowledge",
                       json={"actor": "api-test"}).status_code == 404
    assert client.post(f"/api/v1/alerts/{1}/acknowledge", json={}).status_code == 422


@pytest.mark.skipif(
    not (ARTIFACTS / "snapshot.json").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)
def test_alert_list_exposes_counts_and_status_fields():
    response = client.get("/api/v1/alerts?limit=5")
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["total"] >= len(body["alerts"])
    assert body["statuses"] == ["open", "acknowledged", "resolved"]
    if body["alerts"]:
        row = body["alerts"][0]
        assert {"status", "acknowledged_at", "resolved_at", "label"} <= set(row)
