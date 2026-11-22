"""Digital-twin service: device registry, sample scoring and twin snapshots."""

from __future__ import annotations

import threading

from sentinel.config import settings
from sentinel.inference.service import SentinelService, get_service
from sentinel.logging_setup import get_logger
from sentinel.replay.service import REPLAY_SENSORS, SENSOR_LABELS
from sentinel.store import devices as device_store
from sentinel.twins import twin as scoring
from sentinel.twins.autofeed import feeder

log = get_logger("twins")

MAX_SAMPLE_SENSORS = 64
MAX_ABS_VALUE = 1e9


def sensor_catalog() -> list[dict]:
    return [{"key": key, "label": SENSOR_LABELS.get(key, key)} for key in REPLAY_SENSORS]


class TwinService:
    def __init__(self, service: SentinelService | None = None) -> None:
        self._service = service
        self._baselines: dict[str, dict] = {}
        self._lock = threading.Lock()

    @property
    def service(self) -> SentinelService:
        if self._service is None:
            self._service = get_service()
        return self._service

    # -- baseline ----------------------------------------------------------
    def baseline(self, asset_id: str | None) -> dict | None:
        if not asset_id:
            return None
        with self._lock:
            cached = self._baselines.get(asset_id)
        if cached is not None:
            return cached
        asset = self.service.asset(asset_id)
        if asset is None:
            return None
        series = (asset.get("series") or {}).get("sensors") or {}
        baseline = scoring.build_baseline(series, settings.healthy_cycle_limit)
        baseline["asset_id"] = asset["id"]
        with self._lock:
            self._baselines[asset["id"]] = baseline
        return baseline

    def model_reference(self, asset_id: str | None) -> dict | None:
        if not asset_id:
            return None
        asset = self.service.asset(asset_id)
        if asset is None:
            return None
        rul = asset.get("rul") or {}
        return {
            "asset_id": asset["id"],
            "label": asset.get("label") or asset["id"],
            "cycle": asset.get("cycle"),
            "lifetime": asset.get("lifetime"),
            "estimate": rul.get("estimate"),
            "lower": rul.get("lower"),
            "upper": rul.get("upper"),
            "status": asset.get("status"),
            "health_score": asset.get("health_score"),
            "note": "Pipeline estimate at the asset's last recorded cycle.",
        }

    # -- ingestion ---------------------------------------------------------
    def validate_sensors(self, sensors: dict) -> dict[str, float]:
        if not sensors:
            raise ValueError("Send at least one sensor channel.")
        if len(sensors) > MAX_SAMPLE_SENSORS:
            raise ValueError(f"At most {MAX_SAMPLE_SENSORS} channels per sample.")
        cleaned: dict[str, float] = {}
        for key, value in sensors.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Sensor channel names must be non-empty strings.")
            number = scoring.finite(value)
            if number is None:
                raise ValueError(f"Sensor {key!r} is not a finite number.")
            if abs(number) > MAX_ABS_VALUE:
                raise ValueError(f"Sensor {key!r} is outside the accepted range.")
            cleaned[key.strip()[:32]] = number
        return cleaned

    def ingest(self, device: dict, sensors: dict, cycle: int | None = None,
               source: str = "manual") -> dict:
        cleaned = self.validate_sensors(sensors)
        baseline = self.baseline(device.get("asset_id"))
        assessment = scoring.assess(cleaned, baseline)
        sample = device_store.append_sample(
            device["device_id"], sensors=cleaned, assessment=assessment,
            cycle=cycle, source=source,
        )
        return {"sample": sample, "twin": assessment}

    def auto_ingest(self, device_id: str, sensors: dict, cycle: int | None,
                    source: str) -> dict:
        device = device_store.get_device(device_id)
        if device is None:
            raise LookupError(f"Unknown device {device_id}")
        return self.ingest(device, sensors, cycle=cycle, source=source)

    # -- snapshots ---------------------------------------------------------
    def twin_snapshot(self, device_id: str, limit: int = 120) -> dict | None:
        device = device_store.get_device(device_id)
        if device is None:
            return None
        samples = device_store.list_samples(device_id, limit=limit)
        latest = samples[-1] if samples else None
        baseline = self.baseline(device.get("asset_id"))
        assessment = scoring.assess(latest["sensors"], baseline) if latest else None
        history = [
            {
                "seq": entry["seq"],
                "at": entry["at"],
                "cycle": entry["cycle"],
                "source": entry["source"],
                "health": entry["health"],
                "anomaly": entry["anomaly"],
                "severity": entry["severity"],
            }
            for entry in samples
        ]
        return {
            "device": device,
            "twin": assessment,
            "latest": latest,
            "history": history,
            "trend": scoring.trend(history),
            "baseline": {
                "asset_id": baseline.get("asset_id"),
                "cycles": baseline.get("cycles"),
                "sensor_count": baseline.get("sensor_count"),
                "channels": baseline.get("channels"),
            } if baseline else None,
            "model": self.model_reference(device.get("asset_id")),
            "auto": feeder.status(device_id),
            "sample_count": device_store.sample_count(device_id),
            "sensors": sensor_catalog(),
        }

    def list_twins(self) -> list[dict]:
        twins = []
        for device in device_store.list_devices():
            snapshot = self.twin_snapshot(device["device_id"], limit=24)
            twins.append({
                "device": device,
                "twin": snapshot["twin"] if snapshot else None,
                "trend": snapshot["trend"] if snapshot else None,
                "model": snapshot["model"] if snapshot else None,
                "auto": feeder.status(device["device_id"]),
                "sample_count": snapshot["sample_count"] if snapshot else 0,
            })
        return twins

    # -- lifecycle ---------------------------------------------------------
    def start_auto(self, device_id: str) -> dict:
        device = device_store.get_device(device_id)
        if device is None:
            raise LookupError(f"Unknown device {device_id}")
        return feeder.start(device, lambda sensors, cycle, source: self.auto_ingest(
            device_id, sensors, cycle, source))

    def stop_auto(self, device_id: str) -> dict:
        feeder.stop(device_id)
        return feeder.status(device_id)


_twin_service: TwinService | None = None


def get_twin_service() -> TwinService:
    global _twin_service
    if _twin_service is None:
        _twin_service = TwinService()
    return _twin_service
