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


class OnboardingMappingRequest(BaseModel):
    """Customer CSV text plus the source-column -> canonical-field mapping."""

    csv_text: str = Field(..., min_length=1)
    mapping: dict[str, str] | None = Field(None, description="source column -> canonical target")
    profile_id: int | None = Field(None, description="Reuse a saved mapping profile")
    source_file: str = Field("upload.csv", max_length=255)


class OnboardingImportRequest(OnboardingMappingRequest):
    name: str = Field(..., min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=500)
    accept_drift: bool = Field(False, description="Acknowledge detected schema drift")


class MappingProfileRequest(BaseModel):
    """A reusable source/vendor mapping and the schema it was built from."""

    name: str = Field(..., min_length=1, max_length=96)
    source: str = Field("", max_length=120)
    mapping: dict[str, str] = Field(..., min_length=1)
    expected_columns: list[str] = Field(..., min_length=1)
    notes: str | None = Field(None, max_length=500)


class DeviceCreate(BaseModel):
    """Register a machine whose telemetry feeds a digital twin."""

    name: str = Field(..., min_length=1, max_length=120)
    asset_id: str | None = Field(None, max_length=48, description="Fleet asset used for the baseline")
    mode: Literal["manual", "auto"] = "manual"
    interval_ms: int = Field(1500, ge=250, le=60_000, description="Auto-mode sample interval")
    notes: str | None = Field(None, max_length=500)
    model_config = {"json_schema_extra": {"example": {
        "name": "Line 3 compressor", "asset_id": "FD001-001", "mode": "manual"
    }}}


class DeviceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    asset_id: str | None = Field(None, max_length=48)
    mode: Literal["manual", "auto"] | None = None
    interval_ms: int | None = Field(None, ge=250, le=60_000)
    notes: str | None = Field(None, max_length=500)


class DeviceTelemetry(BaseModel):
    """One sample from a physical gateway or the manual entry form."""

    sensors: dict[str, float] = Field(..., min_length=1, max_length=64)
    cycle: int | None = Field(None, ge=0, le=10_000_000)
    recorded_at: str | None = Field(None, max_length=40)
    model_config = {"json_schema_extra": {"example": {
        "sensors": {"s2": 642.1, "s3": 1589.4, "s4": 1408.2, "s7": 554.3,
                    "s8": 47.9, "s11": 47.1, "s12": 522.4, "s15": 8.42},
        "cycle": 42,
    }}}


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
