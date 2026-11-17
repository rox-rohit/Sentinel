"""Real-plant onboarding routes: inspect, map, validate, register and score.

The flow is deliberately explicit and stateless:

  POST /onboarding/inspect   raw CSV -> columns, samples, suggested mapping
  POST /onboarding/validate  CSV + mapping -> blocking report
  POST /onboarding/import    validated CSV + mapping -> per-asset parquet + registry
  GET  /onboarding/assets    registered plant assets with their mappings
  POST /onboarding/assets/{id}/score  gate + RUL inference
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sentinel.api.deps import require_api_key, service_dependency
from sentinel.api.schemas import OnboardingImportRequest, OnboardingMappingRequest
from sentinel.inference.service import SentinelService
from sentinel.onboarding.plant import inspect_frame, parse_csv, schema_payload, validate_csv
from sentinel.onboarding.service import OnboardingBlocked, import_csv, score_asset
from sentinel.store.db import get_plant_asset, list_plant_assets

router = APIRouter(tags=["onboarding"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _guard_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 5 MB limit.")


@router.get("/onboarding/schema", summary="Canonical plant telemetry schema and aliases")
def onboarding_schema() -> dict:
    return schema_payload()


@router.post("/onboarding/inspect", summary="Inspect a customer CSV and suggest a column mapping")
async def inspect(request: Request,
                  filename: str = Query("upload.csv", max_length=255)) -> dict:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 5 MB limit.")
    text = body.decode("utf-8-sig", errors="replace")
    try:
        frame = parse_csv(text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    payload = inspect_frame(frame)
    payload["source_file"] = filename
    return payload


@router.post("/onboarding/validate", summary="Validate a mapped CSV before storing anything")
def validate(payload: OnboardingMappingRequest) -> dict:
    _guard_size(payload.csv_text)
    try:
        report = validate_csv(payload.csv_text, payload.mapping,
                              source_file=payload.source_file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    return report


@router.post("/onboarding/import", summary="Register validated plant assets",
             dependencies=[Depends(require_api_key)])
def import_assets(payload: OnboardingImportRequest) -> dict:
    _guard_size(payload.csv_text)
    try:
        return import_csv(name=payload.name, text=payload.csv_text, mapping=payload.mapping,
                          source_file=payload.source_file, notes=payload.notes)
    except OnboardingBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc


@router.get("/onboarding/assets", summary="Registered plant assets and their sensor mappings")
def assets(limit: int = Query(100, ge=1, le=500)) -> dict:
    rows = list_plant_assets(limit)
    return {
        "assets": rows,
        "counts": {
            "total": len(rows),
            "ready": sum(1 for row in rows if row["status"] == "ready"),
            "registered": sum(1 for row in rows if row["status"] != "ready"),
        },
        "note": (
            "Registry entries store the exact source-column mapping used at import, so a "
            "re-import can be reproduced. Status 'ready' means the asset passed validation "
            "and satisfies the current model feature contract."
        ),
    }


@router.get("/onboarding/assets/{registry_id}", summary="One registered plant asset")
def asset(registry_id: int) -> dict:
    record = get_plant_asset(registry_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown plant asset {registry_id}")
    return record


@router.post("/onboarding/assets/{registry_id}/score",
             summary="Score a registered asset, after the eligibility gate",
             dependencies=[Depends(require_api_key)])
def score(registry_id: int, service: SentinelService = Depends(service_dependency)) -> dict:
    result = score_asset(registry_id, service)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"Unknown plant asset {registry_id}")
    if not result.get("eligible"):
        raise HTTPException(
            status_code=422,
            detail="Scoring blocked: " + "; ".join(result.get("reasons", [])),
        )
    return result


@router.post("/onboarding/parse-preview", summary="Parse only, returning a small preview",
             include_in_schema=False)
async def parse_preview(request: Request, limit: int = Query(5, ge=1, le=20)) -> dict:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body.")
    text = body.decode("utf-8-sig", errors="replace")
    try:
        frame = parse_csv(text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "preview": frame.head(limit).to_dict(orient="records"),
    }
