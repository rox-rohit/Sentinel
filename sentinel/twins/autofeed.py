"""Auto mode: drive a twin from recorded telemetry on a background thread.

Auto mode is an ingest *source*, not a different scoring path. It steps through
the bound asset's recorded C-MAPSS trajectory at the device's interval and
forwards each frame through the same ingestion function a physical gateway
would call. Nothing is generated: the frame values are the build artifact's.

The feeder deliberately uses a thread rather than an asyncio task: the API can
serve a twin from a thread-pool route handler, and a restartable background
thread is straightforward to reason about and to stop in tests.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable

from sentinel.logging_setup import get_logger
from sentinel.replay.service import get_replay_service

log = get_logger("twins.autofeed")

MIN_INTERVAL_MS = 250
MAX_INTERVAL_MS = 60_000


class AutoFeeder:
    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def status(self, device_id: str) -> dict:
        with self._lock:
            run = self._runs.get(device_id)
            if run is None:
                return {"running": False, "cursor": None, "total_cycles": None,
                        "started_at": None, "finished": False, "error": None}
            return {
                "running": bool(run["thread"].is_alive()) and not run["stop"].is_set(),
                "cursor": run["state"]["cursor"],
                "total_cycles": run["state"]["total"],
                "started_at": run["state"]["started_at"],
                "finished": run["state"]["finished"],
                "error": run["state"]["error"],
            }

    def start(self, device: dict, ingest: Callable[..., dict]) -> dict:
        device_id = device["device_id"]
        asset_id = device.get("asset_id")
        if not asset_id:
            raise ValueError(
                "Auto mode needs a fleet asset bound to the twin; bind one first."
            )
        replay = get_replay_service()
        if not replay.available():
            raise LookupError(
                "No replay artifact is available. Run `python -m sentinel.pipelines.build`."
            )
        player = replay.player(asset_id)
        if player is None:
            raise LookupError(f"No recorded telemetry for asset {asset_id}.")
        player.restart()

        self.stop(device_id)
        stop = threading.Event()
        interval = max(MIN_INTERVAL_MS, min(MAX_INTERVAL_MS, int(device.get("interval_ms") or 1500))) / 1000.0
        state = {
            "cursor": 0,
            "total": player.total_cycles,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished": False,
            "error": None,
        }

        def loop() -> None:
            log.info("twin auto feed started: %s (%s)", device_id, asset_id)
            while not stop.is_set():
                frame = player.step()
                if frame is None:
                    state["finished"] = True
                    break
                sensors = {
                    key: value for key, value in (frame.get("sensors") or {}).items()
                    if isinstance(value, (int, float))
                }
                try:
                    ingest(sensors, frame.get("cycle"), "auto")
                except Exception as exc:  # keep the feed alive, report the failure
                    log.warning("twin auto ingest failed for %s: %s", device_id, exc)
                    state["error"] = str(exc)
                state["cursor"] = int(frame.get("cycle") or 0)
                stop.wait(interval)
            log.info("twin auto feed stopped: %s at cycle %s", device_id, state["cursor"])

        thread = threading.Thread(target=loop, daemon=True, name=f"twin-feed-{device_id}")
        with self._lock:
            self._runs[device_id] = {"thread": thread, "stop": stop, "state": state}
        thread.start()
        return self.status(device_id)

    def stop(self, device_id: str) -> bool:
        with self._lock:
            run = self._runs.pop(device_id, None)
        if run is None:
            return False
        run["stop"].set()
        return True

    def stop_all(self) -> None:
        with self._lock:
            device_ids = list(self._runs)
        for device_id in device_ids:
            self.stop(device_id)


feeder = AutoFeeder()
