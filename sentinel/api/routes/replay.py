"""Replay routes: recorded telemetry streamed over WebSocket.

The stream is explicitly a replay of recorded C-MAPSS trajectories. Query
parameters only control pacing; they never change the data.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from sentinel.api.deps import service_dependency
from sentinel.inference.service import SentinelService
from sentinel.logging_setup import get_logger
from sentinel.replay.service import (BASE_INTERVAL_SECONDS, MAX_SPEED, MIN_SPEED,
                                     REPLAY_SENSORS, SENSOR_LABELS, get_replay_service)

log = get_logger("api.replay")

router = APIRouter(tags=["replay"])


@router.get("/replay/units", summary="Units available for telemetry replay")
def replay_units(service: SentinelService = Depends(service_dependency)) -> dict:
    replay = get_replay_service()
    statuses = {asset["id"]: asset["status"] for asset in service.assets()}
    units = replay.units()
    for unit in units:
        unit["status"] = statuses.get(unit["id"])
    return {
        "available": replay.available(),
        "units": units,
        "sensors": [{"key": s, "label": SENSOR_LABELS[s]} for s in REPLAY_SENSORS],
        "protocol": {
            "base_interval_seconds": BASE_INTERVAL_SECONDS,
            "speed_range": [MIN_SPEED, MAX_SPEED],
            "commands": ["pause", "resume", "speed", "seek", "restart"],
        },
        "disclaimer": (
            "Simulated replay of recorded C-MAPSS trajectories with pipeline estimates. "
            "Not a live sensor feed."
        ),
    }


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})


@router.websocket("/ws/replay/{asset_id}")
async def replay_stream(
    websocket: WebSocket,
    asset_id: str,
    speed: float = Query(1.0, ge=MIN_SPEED, le=MAX_SPEED),
    start_cycle: int = Query(0, ge=0),
    interval_ms: float | None = Query(
        None, ge=20, le=5000,
        description="Pacing override for tests and slow clients; does not change data.",
    ),
) -> None:
    replay = get_replay_service()
    player = replay.player(asset_id, speed=speed, start_cycle=start_cycle, interval_ms=interval_ms)
    await websocket.accept()

    if player is None:
        await _send_error(
            websocket, "unknown_asset",
            f"No replay track for {asset_id}. Available: {[u['id'] for u in replay.units()][:5]}",
        )
        await websocket.close(code=4404)
        return

    try:
        meta = replay.meta(asset_id, speed=player.speed)
    except KeyError:
        await _send_error(websocket, "unknown_asset", f"No replay track for {asset_id}")
        await websocket.close(code=4404)
        return

    await websocket.send_json(meta)
    if start_cycle:
        player.seek(start_cycle)
    log.info("replay stream opened: %s (%.2fx)", asset_id, player.speed)

    seq = 0
    try:
        while True:
            frame = player.step()
            if frame is not None:
                seq += 1
                await websocket.send_json({
                    "type": "frame",
                    "seq": seq,
                    "asset_id": asset_id.upper(),
                    "total_cycles": player.total_cycles,
                    **frame,
                })
            elif player.finished and player.playing:
                player.pause()
                await websocket.send_json({
                    "type": "end",
                    "asset_id": asset_id.upper(),
                    "cycle": player.current_cycle,
                    "total_cycles": player.total_cycles,
                })

            try:
                if player.playing:
                    command = await asyncio.wait_for(
                        websocket.receive_json(), timeout=player.interval()
                    )
                else:
                    # Paused or finished: block until the client asks for something.
                    command = await websocket.receive_json()
            except TimeoutError:
                continue
            except WebSocketDisconnect:
                log.info("replay stream closed: %s", asset_id)
                return

            action = str(command.get("action", "")).lower() if isinstance(command, dict) else ""

            if action in {"pause", "stop"}:
                player.pause()
            elif action in {"resume", "play"}:
                player.resume()
            elif action == "speed":
                try:
                    player.set_speed(float(command.get("speed", player.speed)))
                except (TypeError, ValueError):
                    await _send_error(websocket, "bad_command", "speed must be numeric")
            elif action == "seek":
                try:
                    player.seek(int(command.get("cycle", player.current_cycle)))
                except (TypeError, ValueError):
                    await _send_error(websocket, "bad_command", "cycle must be an integer")
            elif action == "restart":
                player.restart()
            else:
                await _send_error(
                    websocket, "bad_command",
                    f"Unknown action {action!r}; expected pause, resume, speed, seek or restart.",
                )

            await websocket.send_json(player.state())
    except WebSocketDisconnect:
        log.info("replay stream disconnected: %s", asset_id)
