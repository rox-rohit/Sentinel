"""Telemetry replay over recorded C-MAPSS trajectories.

The replay stream is *recorded data*, not a simulator: every frame is one cycle
of a held-out C-MAPSS test engine, together with the estimates the build
pipeline already produced for that cycle (RUL, horizon risk, anomaly score,
health). Nothing is generated at request time, and no sensor value is invented.

`artifacts/replay.parquet` is written by `python -m sentinel.pipelines.build`.
"""

from __future__ import annotations

import threading
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from sentinel.config import settings
from sentinel.logging_setup import get_logger

log = get_logger("replay")

REPLAY_SENSORS: tuple[str, ...] = ("s2", "s3", "s4", "s7", "s8", "s11", "s12", "s15")
SENSOR_LABELS = {
    "s2": "Fan inlet pressure (P2)",
    "s3": "LPC outlet temperature (T24)",
    "s4": "LPC outlet pressure (P24)",
    "s7": "HPC outlet pressure (Ps30)",
    "s8": "Fuel flow ratio (phi)",
    "s11": "HPC outlet static pressure (Ps30)",
    "s12": "LPT outlet temperature (T50)",
    "s15": "Bypass ratio (BPR)",
}

BASE_INTERVAL_SECONDS = 0.7
MIN_SPEED = 0.25
MAX_SPEED = 8.0
MIN_INTERVAL_MS = 20.0
MAX_INTERVAL_MS = 5000.0
MAX_BUFFER = 400


def clamp_speed(value: float) -> float:
    return max(MIN_SPEED, min(MAX_SPEED, float(value)))


def clamp_interval_ms(value: float | None) -> float | None:
    if value is None:
        return None
    return max(MIN_INTERVAL_MS, min(MAX_INTERVAL_MS, float(value)))


def _finite(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 4) if math.isfinite(number) else None


@dataclass
class ReplayPlayer:
    """Cursor over one recorded trajectory.

    Pure control logic (no asyncio, no HTTP) so ordering, pausing and speed are
    unit-testable.
    """

    frames: list[dict]
    speed: float = 1.0
    cursor: int = 0
    playing: bool = True
    interval_override: float | None = None
    total_cycles: int = field(init=False)

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("A replay player needs at least one frame.")
        self.speed = clamp_speed(self.speed)
        self.total_cycles = int(self.frames[-1]["cycle"])
        self.seek(self.frames[min(self.cursor, len(self.frames) - 1)]["cycle"])

    # -- state -------------------------------------------------------------
    @property
    def finished(self) -> bool:
        return self.cursor >= len(self.frames)

    @property
    def current_cycle(self) -> int:
        index = min(self.cursor, len(self.frames) - 1)
        return int(self.frames[index]["cycle"])

    def interval(self) -> float:
        if self.interval_override is not None:
            return self.interval_override
        return BASE_INTERVAL_SECONDS / self.speed

    # -- controls ----------------------------------------------------------
    def set_speed(self, speed: float) -> float:
        self.speed = clamp_speed(speed)
        return self.speed

    def seek(self, cycle: int) -> int:
        target = max(0, int(cycle))
        index = 0
        for position, frame in enumerate(self.frames):
            if int(frame["cycle"]) >= target:
                index = position
                break
        else:
            index = len(self.frames)
        self.cursor = index
        return self.current_cycle

    def restart(self) -> None:
        self.cursor = 0
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def resume(self) -> None:
        if self.finished:
            self.restart()
        else:
            self.playing = True

    def step(self) -> dict | None:
        """Return the next frame and advance, or ``None`` at end of stream."""
        if not self.playing or self.finished:
            return None
        frame = self.frames[self.cursor]
        self.cursor += 1
        return frame

    def state(self) -> dict:
        return {
            "type": "state",
            "playing": self.playing,
            "speed": self.speed,
            "cycle": self.current_cycle,
            "total_cycles": self.total_cycles,
        }


class ReplayService:
    """Loads the replay artifact once and serves read-only frame lists."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.artifacts_dir / "replay.parquet")
        self._tracks: dict[str, list[dict]] | None = None
        self._mtime = 0.0
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self.path.exists()

    def _load(self) -> dict[str, list[dict]]:
        if not self.path.exists():
            return {}
        mtime = self.path.stat().st_mtime
        if self._tracks is None or mtime != self._mtime:
            with self._lock:
                frame = pd.read_parquet(self.path)
                tracks: dict[str, list[dict]] = {}
                for asset_id, group in frame.groupby("asset_id", sort=True):
                    ordered = group.sort_values("cycle")
                    tracks[f"FD001-{int(asset_id):03d}"] = [
                        self._frame(row) for row in ordered.to_dict("records")
                    ]
                self._tracks = tracks
                self._mtime = mtime
                log.info("loaded replay tracks: %d units", len(tracks))
        return self._tracks

    @staticmethod
    def _frame(row: dict) -> dict:
        severity = row.get("anomaly_severity")
        sensors = {
            sensor: _finite(row.get(sensor))
            for sensor in REPLAY_SENSORS
            if sensor in row
        }
        return {
            "cycle": int(row["cycle"]),
            "rul_estimate": _finite(row.get("predicted_rul")),
            "rul_lower": _finite(row.get("lower")),
            "rul_upper": _finite(row.get("upper")),
            "risk_30": _finite(row.get("risk_30")),
            "health": _finite(row.get("health")),
            "anomaly_score": _finite(row.get("anomaly_score")),
            # Parquet stores a missing category as NaN; JSON must receive null.
            "anomaly_severity": severity if isinstance(severity, str) else None,
            "sensors": sensors,
        }

    def units(self) -> list[dict]:
        tracks = self._load()
        return [
            {
                "id": asset_id,
                "label": f"Unit {asset_id.split('-')[-1]}",
                "cycles": len(frames),
                "first_cycle": int(frames[0]["cycle"]),
                "last_cycle": int(frames[-1]["cycle"]),
            }
            for asset_id, frames in tracks.items()
        ]

    def frames(self, asset_id: str) -> list[dict] | None:
        return self._load().get(asset_id.upper())

    def player(self, asset_id: str, *, speed: float = 1.0,
               start_cycle: int = 0, interval_ms: float | None = None) -> ReplayPlayer | None:
        frames = self.frames(asset_id)
        if not frames:
            return None
        interval = clamp_interval_ms(interval_ms)
        return ReplayPlayer(
            frames=frames,
            speed=speed,
            cursor=0,
            interval_override=(interval / 1000.0) if interval is not None else None,
        )

    def meta(self, asset_id: str, *, speed: float = 1.0) -> dict:
        frames = self.frames(asset_id)
        if not frames:
            raise KeyError(asset_id)
        present = [s for s in REPLAY_SENSORS if s in frames[0]["sensors"]]
        return {
            "type": "meta",
            "asset_id": asset_id.upper(),
            "label": f"Unit {asset_id.upper().split('-')[-1]}",
            "total_cycles": int(frames[-1]["cycle"]),
            "first_cycle": int(frames[0]["cycle"]),
            "speed": clamp_speed(speed),
            "base_interval_ms": round(BASE_INTERVAL_SECONDS * 1000 / clamp_speed(speed)),
            "sensors": [
                {"key": sensor, "label": SENSOR_LABELS.get(sensor, sensor)} for sensor in present
            ],
            "source": (
                "Recorded NASA C-MAPSS FD001 held-out test trajectory; RUL, risk, anomaly "
                "and health are build-pipeline estimates for the same cycle."
            ),
            "disclaimer": (
                "Simulated replay of recorded data. No live sensor connection exists and "
                "nothing here is a real-time plant measurement."
            ),
        }


_service: ReplayService | None = None


def get_replay_service() -> ReplayService:
    global _service
    if _service is None:
        _service = ReplayService()
    return _service
