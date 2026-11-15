"""Prediction routes: failure classification, explanations, RUL, analytics pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from sentinel.api.deps import require_api_key, service_dependency
from sentinel.api.schemas import FailureInput, RULRequest
from sentinel.inference.service import SentinelService

router = APIRouter(tags=["predictions"])


@router.get("/predictions", summary="Predictive analytics payload")
def predictive(service: SentinelService = Depends(service_dependency)) -> dict:
    return service.snapshot()["predictive"]


@router.post("/predict/failure", summary="Score one AI4I process record",
             dependencies=[Depends(require_api_key)])
def predict_failure(payload: FailureInput,
                    service: SentinelService = Depends(service_dependency)) -> dict:
    return service.predict_failure(payload.model_dump())


@router.post("/predict/failure/explain", summary="Local attribution for one process record",
             dependencies=[Depends(require_api_key)])
def explain_failure(payload: FailureInput,
                    service: SentinelService = Depends(service_dependency)) -> dict:
    return service.explain_failure(payload.model_dump())


@router.get("/rul", summary="RUL benchmark, uncertainty and fleet estimates")
def rul(service: SentinelService = Depends(service_dependency)) -> dict:
    return service.snapshot()["rul"]


@router.post("/predict/rul", summary="Predict RUL from a sensor sequence",
             dependencies=[Depends(require_api_key)])
def predict_rul(payload: RULRequest,
                service: SentinelService = Depends(service_dependency)) -> dict:
    return service.predict_rul(payload.readings)


@router.get("/anomalies", summary="Anomaly centre payload")
def anomalies(service: SentinelService = Depends(service_dependency)) -> dict:
    return service.snapshot()["anomalies"]


@router.get("/explainability", summary="Global and local model explanations")
def explainability(service: SentinelService = Depends(service_dependency)) -> dict:
    return service.snapshot()["explainability"]
