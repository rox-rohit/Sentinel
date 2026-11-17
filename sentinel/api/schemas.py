"""Request/response schemas for the versioned API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FailureInput(BaseModel):
    air_temp_k: float = Field(..., ge=200, le=500, description="Ambient air temperature (K)")
    process_temp_k: float = Field(..., ge=200, le=600, description="Process temperature (K)")
    rotational_speed_rpm: float = Field(..., ge=0, le=20000)
    torque_nm: float = Field(..., ge=0, le=2000)
    tool_wear_min: float = Field(..., ge=0, le=1000)
    product_type: Literal["L", "M", "H"] = "M"

    model_config = {
        "json_schema_extra": {
            "example": {
                "air_temp_k": 298.1,
                "process_temp_k": 308.6,
                "rotational_speed_rpm": 1551,
                "torque_nm": 42.8,
                "tool_wear_min": 0,
                "product_type": "M",
            }
        }
    }


class AlertActionRequest(BaseModel):
    """Actor and optional note recorded on an alert lifecycle transition."""

    actor: str = Field(..., min_length=1, max_length=80, description="Who performed the action")
    note: str | None = Field(None, max_length=500, description="Optional audit note")


class RULRequest(BaseModel):
    readings: list[dict[str, float]] = Field(
        ...,
        min_length=30,
        description=(
            "Chronological cycles. Each item needs a cycle plus NASA C-MAPSS sensor keys "
            "s1..s21; op1..op3 default to 0 when omitted."
        ),
    )


class MaintenanceAsset(BaseModel):
    asset_id: str
    failure_risk: float = Field(..., ge=0, le=1)
    predicted_rul: float = Field(..., ge=0)
    criticality: int = Field(2, ge=1, le=3)
    planned_cost: float | None = Field(None, ge=0)
    expected_failure_cost: float | None = Field(None, ge=0)


class MaintenanceRequest(BaseModel):
    budget: float = Field(..., gt=0, le=1_000_000)
    assets: list[MaintenanceAsset] | None = None


class MaintenanceScenarioRequest(BaseModel):
    """Save the optimisation result for a budget under a comparable name."""

    name: str = Field(..., min_length=1, max_length=80)
    budget: float = Field(..., gt=0, le=1_000_000)
    note: str | None = Field(None, max_length=500)
    assets: list[MaintenanceAsset] | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    product: str
    snapshot_age_seconds: float
    build_version: str
