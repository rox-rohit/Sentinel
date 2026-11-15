"""Replay tests: cursor semantics (pure) and the WebSocket protocol (ASGI)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sentinel.api.main import app
from sentinel.config import ARTIFACTS
from sentinel.replay.service import ReplayPlayer, ReplayService, clamp_speed

client = TestClient(app)

requires_artifacts = pytest.mark.skipif(
    not (ARTIFACTS / "replay.parquet").exists(),
    reason="run `python -m sentinel.pipelines.build` first",
)


def make_frames(count: int = 10) -> list[dict]:
    return [
        {
            "cycle": cycle,
            "rul_estimate": 100.0 - cycle,
            "health": 90.0 - cycle,
            "anomaly_score": cycle * 0.1,
            "anomaly_severity": "normal",
            "sensors": {"s2": 640.0 + cycle},
        }
        for cycle in range(1, count + 1)
    ]


def test_player_orders_frames_and_stops_at_the_end():
    player = ReplayPlayer(frames=make_frames(3))
    assert [player.step()["cycle"] for _ in range(3)] == [1, 2, 3]
    assert player.finished
    assert player.step() is None


def test_pause_resume_and_restart():
    player = ReplayPlayer(frames=make_frames(5))
    player.step()
    player.pause()
    assert player.step() is None
    player.resume()
    assert player.step()["cycle"] == 2
    player.restart()
    assert player.step()["cycle"] == 1


def test_seek_lands_on_the_next_available_cycle():
    player = ReplayPlayer(frames=make_frames(10))
    assert player.seek(5) == 5
    assert player.step()["cycle"] == 5
    player.seek(0)
    assert player.step()["cycle"] == 1


def test_speed_is_clamped_and_drives_the_interval():
    player = ReplayPlayer(frames=make_frames(2), speed=100)
    assert player.speed == 8.0
    assert player.interval() == pytest.approx(0.7 / 8.0)
    assert clamp_speed(0.01) == 0.25
    assert player.set_speed(2) == 2.0


def test_frames_are_strict_json_safe():
    """NaN from parquet must become null: browsers reject NaN JSON."""
    frame = ReplayService._frame({
        "cycle": 7,
        "predicted_rul": float("nan"),
        "lower": 10.0,
        "upper": float("inf"),
        "risk_30": 0.25,
        "health": 61.2,
        "anomaly_score": float("nan"),
        "anomaly_severity": float("nan"),
        "s2": float("nan"),
    })
    json.dumps(frame, allow_nan=False)
    assert frame["anomaly_severity"] is None
    assert frame["rul_estimate"] is None
    assert frame["sensors"]["s2"] is None


@requires_artifacts
def test_replay_units_come_from_the_build_artifact():
    response = client.get("/api/v1/replay/units")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["units"]
    unit = body["units"][0]
    assert unit["id"].startswith("FD001-")
    assert unit["cycles"] > 0
    assert unit["status"] in {"healthy", "attention", "warning", "critical"}


@requires_artifacts
def test_websocket_streams_ordered_frames_and_accepts_controls():
    path = "/api/v1/ws/replay/FD001-001?interval_ms=25&speed=4"
    with client.websocket_connect(path) as websocket:
        meta = websocket.receive_json()
        assert meta["type"] == "meta"
        assert meta["total_cycles"] > 0
        assert meta["sensors"]

        first = websocket.receive_json()
        second = websocket.receive_json()
        assert first["type"] == "frame" and second["type"] == "frame"
        assert second["seq"] == first["seq"] + 1
        assert second["cycle"] == first["cycle"] + 1
        assert set(first["sensors"]) <= {sensor["key"] for sensor in meta["sensors"]}

        websocket.send_json({"action": "pause"})
        message = websocket.receive_json()
        while message["type"] == "frame":
            message = websocket.receive_json()
        assert message["type"] == "state" and message["playing"] is False

        websocket.send_json({"action": "speed", "speed": 2})
        message = websocket.receive_json()
        while message["type"] == "frame":
            message = websocket.receive_json()
        assert message["type"] == "state" and message["speed"] == 2

        websocket.send_json({"action": "seek", "cycle": 20})
        message = websocket.receive_json()
        while message["type"] == "frame":
            message = websocket.receive_json()
        assert message["cycle"] >= 20

        websocket.send_json({"action": "restart"})
        message = websocket.receive_json()
        while message["type"] == "frame":
            message = websocket.receive_json()
        assert message["cycle"] == 1 and message["playing"] is True


@requires_artifacts
def test_unknown_replay_asset_is_rejected():
    with client.websocket_connect("/api/v1/ws/replay/DOES-NOT-EXIST") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert message["code"] == "unknown_asset"
