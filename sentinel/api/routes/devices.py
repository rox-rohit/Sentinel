"""Digital-twin routes: registry, ingest, auto feed and twin snapshots.

Two authentication paths exist on purpose:

* a physical gateway or PLC bridge sends ``X-Device-Token`` (issued once at
  registration, stored only as a PBKDF2 digest);
* an operator console sends the platform ``X-API-Key`` (when one is configured).

Unknown or missing credentials are rejected — ingest is never anonymous.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from sentinel.api.deps import api_key_valid, require_api_key
from sentinel.api.schemas import DeviceCreate, DeviceTelemetry, DeviceUpdate
from sentinel.replay.service import BASE_INTERVAL_SECONDS
from sentinel.store import devices as store
from sentinel.twins import get_twin_service, sensor_catalog
from sentinel.twins.autofeed import MAX_INTERVAL_MS, MIN_INTERVAL_MS

router = APIRouter(tags=["twins"])

MAX_INGEST_PER_SECOND = 25
_ingest_windows: dict[str, deque[float]] = defaultdict(deque)


def _throttle(device_id: str) -> None:
    now = time.monotonic()
    window = _ingest_windows[device_id]
    while window and now - window[0] > 1.0:
        window.popleft()
    if len(window) >= MAX_INGEST_PER_SECOND:
        raise HTTPException(
            status_code=429,
            detail=f"Ingest is limited to {MAX_INGEST_PER_SECOND} samples per second per device.",
        )
    window.append(now)


async def require_ingest_auth(
    device_id: str,
    x_device_token: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict:
    if x_device_token and store.verify_token(device_id, x_device_token):
        device = store.get_device(device_id)
        if device is not None:
            return device
    if x_api_key and api_key_valid(x_api_key):
        device = store.get_device(device_id)
        if device is not None:
            return device
    if store.get_device(device_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown device {device_id}")
    raise HTTPException(
        status_code=401,
        detail="Send X-Device-Token for this device, or a valid X-API-Key.",
    )


@router.get("/devices/schema", summary="Twin sensor catalogue and ingest contract")
def devices_schema() -> dict:
    return {
        "sensors": sensor_catalog(),
        "modes": ["manual", "auto"],
        "ingest": {
            "method": "POST",
            "path": "/devices/{device_id}/telemetry",
            "headers": {"X-Device-Token": "token returned at registration"},
            "body": {"sensors": {"s2": 642.1}, "cycle": 42, "recorded_at": "ISO-8601"},
            "limits": {
                "max_channels": 64,
                "max_ingest_per_second": MAX_INGEST_PER_SECOND,
                "max_body_bytes": 8 * 1024 * 1024,
            },
        },
        "auto_mode": {
            "description": (
                "Auto mode feeds the twin from the bound asset's recorded trajectory "
                "at the device interval. It is an ingest source, not a simulation."
            ),
            "base_interval_seconds": BASE_INTERVAL_SECONDS,
            "interval_ms_range": [MIN_INTERVAL_MS, MAX_INTERVAL_MS],
        },
        "scoring": {
            "method": "median/robust-scale deviation against the asset's healthy cycles",
            "health": "100 - min(50, 11 x (0.65 peak|z| + 0.35 median|z|)) - 20 x (1 - coverage)",
            "bands": {"healthy": 80, "attention": 60, "warning": 40},
        },
    }


@router.post("/devices", summary="Register a machine and issue its ingest token",
             dependencies=[Depends(require_api_key)])
def create_device(payload: DeviceCreate) -> dict:
    device = store.create_device(
        name=payload.name, asset_id=payload.asset_id, mode=payload.mode,
        interval_ms=payload.interval_ms, notes=payload.notes,
    )
    twins = get_twin_service()
    snapshot = twins.twin_snapshot(device["device_id"], limit=1)
    return {
        "device": device,
        "token": device.get("token"),
        "twin": snapshot,
        "notice": "The token is shown once. Store it on the gateway, not in source control.",
    }


@router.get("/devices", summary="Registered twins with their latest state")
def list_devices() -> dict:
    twins = get_twin_service().list_twins()
    return {
        "twins": twins,
        "counts": {
            "total": len(twins),
            "auto": sum(1 for entry in twins if entry["device"]["mode"] == "auto"),
            "reporting": sum(1 for entry in twins if entry["device"]["last_seen_at"]),
        },
        "sensors": sensor_catalog(),
    }


@router.get("/devices/{device_id}", summary="One twin: state, history and baseline")
def device(device_id: str, limit: int = Query(120, ge=1, le=600)) -> dict:
    snapshot = get_twin_service().twin_snapshot(device_id, limit=limit)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Unknown device {device_id}")
    return snapshot


@router.patch("/devices/{device_id}", summary="Rename, re-bind or re-mode a twin",
              dependencies=[Depends(require_api_key)])
def update(device_id: str, payload: DeviceUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("mode") == "manual":
        get_twin_service().stop_auto(device_id)
    device = store.update_device(device_id, **changes)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Unknown device {device_id}")
    return device


@router.delete("/devices/{device_id}", summary="Remove a twin and its samples",
               dependencies=[Depends(require_api_key)])
def remove(device_id: str) -> dict:
    get_twin_service().stop_auto(device_id)
    if not store.delete_device(device_id):
        raise HTTPException(status_code=404, detail=f"Unknown device {device_id}")
    return {"deleted": True, "device_id": device_id}


@router.post("/devices/{device_id}/rotate-token", summary="Issue a new ingest token",
             dependencies=[Depends(require_api_key)])
def rotate(device_id: str) -> dict:
    device = store.rotate_token(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Unknown device {device_id}")
    return {
        "device": device,
        "token": device.get("token"),
        "notice": "The previous token stops working immediately.",
    }


@router.post("/devices/{device_id}/telemetry",
             summary="Ingest one telemetry sample from a machine")
def telemetry(device_id: str, payload: DeviceTelemetry,
              device: dict = Depends(require_ingest_auth)) -> dict:
    _throttle(device_id)
    if payload.recorded_at:
        try:
            datetime.fromisoformat(payload.recorded_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="recorded_at must be ISO-8601.") from exc
    result = get_twin_service().ingest(device, payload.sensors, cycle=payload.cycle, source="manual")
    return {
        "accepted": True,
        "device_id": device_id,
        "sample": result["sample"],
        "twin": result["twin"],
    }


@router.post("/devices/{device_id}/auto/start", summary="Start auto mode",
             dependencies=[Depends(require_api_key)])
def start_auto(device_id: str) -> dict:
    try:
        status = get_twin_service().start_auto(device_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"device_id": device_id, "auto": status}


@router.post("/devices/{device_id}/auto/stop", summary="Stop auto mode",
             dependencies=[Depends(require_api_key)])
def stop_auto(device_id: str) -> dict:
    if store.get_device(device_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown device {device_id}")
    return {"device_id": device_id, "auto": get_twin_service().stop_auto(device_id)}
