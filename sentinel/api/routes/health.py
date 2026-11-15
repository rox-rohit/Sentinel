"""Health and system status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from sentinel.api.deps import service_dependency
from sentinel.inference.service import SentinelService

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness and artifact readiness")
def health(service: SentinelService = Depends(service_dependency)) -> dict:
    status = service.system_status()
    return {
        "status": status["status"],
        "product": status["product"],
        "snapshot_age_seconds": status["snapshot"]["age_seconds"],
        "build_version": status["snapshot"]["build_version"],
        "artifacts_ready": all(status["artifacts"].values()),
    }


@router.get("/system/status", summary="Full system status")
def system_status(service: SentinelService = Depends(service_dependency)) -> dict:
    return service.system_status()
