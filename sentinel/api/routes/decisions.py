"""Decision routes: maintenance optimisation, saved scenario comparison and settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from sentinel.api.deps import require_api_key, service_dependency
from sentinel.api.schemas import MaintenanceRequest, MaintenanceScenarioRequest
from sentinel.decision.scenarios import compare_saved
from sentinel.inference.service import SentinelService
from sentinel.store.db import (delete_scenario, get_scenario, list_scenarios, save_scenario)

router = APIRouter(tags=["decisions"])


def _plan_for(payload: MaintenanceScenarioRequest,
              service: SentinelService) -> dict:
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


@router.get("/maintenance/scenarios", summary="Saved optimisation scenarios")
def scenarios() -> dict:
    return {"scenarios": list_scenarios()}


@router.post("/maintenance/scenarios", summary="Optimise and save a scenario",
             dependencies=[Depends(require_api_key)])
def create_scenario(payload: MaintenanceScenarioRequest,
                    service: SentinelService = Depends(service_dependency)) -> dict:
    plan = _plan_for(payload, service)
    return save_scenario(payload.name, plan, payload.note)


@router.get("/maintenance/scenarios/compare", summary="Compare saved scenarios side by side")
def compare(ids: list[int] = Query(..., min_length=2, max_length=6)) -> dict:
    try:
        return compare_saved(ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown scenario {exc.args[0]}") from exc


@router.get("/maintenance/scenarios/{scenario_id}", summary="One saved scenario with its plan")
def scenario(scenario_id: int) -> dict:
    record = get_scenario(scenario_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario {scenario_id}")
    return record


@router.delete("/maintenance/scenarios/{scenario_id}", summary="Delete a saved scenario",
               dependencies=[Depends(require_api_key)])
def remove_scenario(scenario_id: int) -> dict:
    if not delete_scenario(scenario_id):
        raise HTTPException(status_code=404, detail=f"Unknown scenario {scenario_id}")
    return {"deleted": True, "id": scenario_id}


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
