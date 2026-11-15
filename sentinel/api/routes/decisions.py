"""Decision routes: maintenance optimisation and reference settings."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from sentinel.api.deps import require_api_key, service_dependency
from sentinel.api.schemas import MaintenanceRequest
from sentinel.inference.service import SentinelService

router = APIRouter(tags=["decisions"])


@router.get("/maintenance", summary="Current maintenance plan and scenario comparison")
def maintenance(
    budget: float | None = Query(None, gt=0, le=1_000_000),
    service: SentinelService = Depends(service_dependency),
) -> dict:
    snapshot = service.snapshot()["maintenance"]
    if budget is None or abs(budget - float(snapshot["budget"])) < 1e-6:
        return snapshot
    return service.optimize_maintenance(budget)


@router.post("/maintenance/optimize", summary="Re-optimise with a new budget or asset set",
             dependencies=[Depends(require_api_key)])
def optimize(payload: MaintenanceRequest,
             service: SentinelService = Depends(service_dependency)) -> dict:
    assets = None
    if payload.assets:
        assets = [
            {
                "asset_id": asset.asset_id,
                "failure_risk": asset.failure_risk,
                "predicted_rul": asset.predicted_rul,
                "criticality": asset.criticality,
                "planned_cost": asset.planned_cost,
                "expected_failure_cost": asset.expected_failure_cost,
            }
            for asset in payload.assets
        ]
    return service.optimize_maintenance(payload.budget, assets)


@router.get("/settings", summary="Cost model, health weights and thresholds")
def settings_payload(service: SentinelService = Depends(service_dependency)) -> dict:
    return service.snapshot()["settings"]


@router.get("/drift", summary="Feature drift (PSI) report")
def drift(service: SentinelService = Depends(service_dependency)) -> dict:
    return service.snapshot()["drift"]


@router.post("/system/reload", summary="Reload snapshot artifacts from disk",
             dependencies=[Depends(require_api_key)])
def reload_artifacts(service: SentinelService = Depends(service_dependency)) -> dict:
    service.clear_cache()
    status = service.system_status()
    return {"reloaded": True, "build_version": status["snapshot"]["build_version"]}
