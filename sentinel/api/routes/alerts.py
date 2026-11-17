"""Alert lifecycle routes: list, acknowledge and resolve.

Transitions are persisted in the metadata store, not in the snapshot, so the
state survives a rebuild. Every mutation records the actor and timestamp.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from sentinel.api.deps import require_api_key
from sentinel.api.schemas import AlertActionRequest
from sentinel.store.db import (ALERT_STATUSES, acknowledge_alert, alert_counts, get_alert,
                               list_alerts, resolve_alert)

router = APIRouter(tags=["alerts"])


@router.get("/alerts", summary="Alert inbox with lifecycle status")
def alerts(
    limit: int = Query(60, ge=1, le=500),
    status: str | None = Query(None, pattern="^(open|acknowledged|resolved)$"),
    asset_id: str | None = Query(None),
) -> dict:
    return {
        "alerts": list_alerts(limit=limit, status=status, asset_id=asset_id),
        "counts": alert_counts(),
        "statuses": list(ALERT_STATUSES),
    }


@router.get("/alerts/{alert_id}", summary="Single alert with lifecycle state")
def alert(alert_id: int) -> dict:
    record = get_alert(alert_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown alert {alert_id}")
    return record


@router.post("/alerts/{alert_id}/acknowledge", summary="Acknowledge an alert",
             dependencies=[Depends(require_api_key)])
def acknowledge(alert_id: int, payload: AlertActionRequest) -> dict:
    try:
        record = acknowledge_alert(alert_id, actor=payload.actor, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown alert {alert_id}")
    return record


@router.post("/alerts/{alert_id}/resolve", summary="Resolve an alert",
             dependencies=[Depends(require_api_key)])
def resolve(alert_id: int, payload: AlertActionRequest) -> dict:
    try:
        record = resolve_alert(alert_id, actor=payload.actor, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown alert {alert_id}")
    return record
