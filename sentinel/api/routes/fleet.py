"""Fleet, asset and alert routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from sentinel.api.deps import service_dependency
from sentinel.inference.service import SentinelService
from sentinel.store.db import list_alerts

router = APIRouter(tags=["fleet"])


def _summary(asset: dict) -> dict:
    return {
        key: asset[key]
        for key in ("id", "asset_id", "label", "dataset", "cycle", "lifetime", "status",
                    "health_score", "rul", "anomaly", "criticality", "degradation")
    }


@router.get("/fleet/summary", summary="Fleet-level KPIs, health and risk distributions")
def fleet_summary(service: SentinelService = Depends(service_dependency)) -> dict:
    snapshot = service.snapshot()
    return {
        "summary": snapshot["fleet"]["summary"],
        "health_distribution": snapshot["fleet"]["health_distribution"],
        "risk_distribution": snapshot["fleet"]["risk_distribution"],
        "health_weights": snapshot["fleet"]["health_weights"],
        "data_source": snapshot["fleet"]["data_source"],
        "meta": {"generated_at": snapshot["meta"]["generated_at"]},
    }


@router.get("/fleet/assets", summary="Asset list with health, RUL and anomaly state")
def fleet_assets(
    status: str | None = Query(None, description="Filter by health category"),
    sort: str = Query("health", pattern="^(health|risk|rul|id)$"),
    service: SentinelService = Depends(service_dependency),
) -> dict:
    assets = service.assets()
    if status:
        assets = [a for a in assets if a["status"] == status]
    keys = {
        "health": lambda a: a["health_score"],
        "risk": lambda a: -a["rul"]["horizon_risk"].get("30", 0),
        "rul": lambda a: a["rul"]["estimate"],
        "id": lambda a: a["asset_id"],
    }
    assets = sorted(assets, key=keys[sort])
    return {"count": len(assets), "assets": [_summary(a) for a in assets]}


@router.get("/fleet/assets/{asset_id}", summary="Single asset with full telemetry series")
def fleet_asset(asset_id: str, service: SentinelService = Depends(service_dependency)) -> dict:
    asset = service.asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset {asset_id}")
    return asset


@router.get("/alerts", summary="Generated operational alerts")
def alerts(limit: int = Query(50, ge=1, le=200)) -> dict:
    return {"alerts": list_alerts(limit)}
