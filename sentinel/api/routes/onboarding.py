"""Real-plant onboarding routes: inspect, map, validate, register and score.

The flow is deliberately explicit and stateless:

  POST /onboarding/inspect   raw CSV -> columns, samples, suggested mapping
  POST /onboarding/validate  CSV + mapping -> blocking report
  POST /onboarding/import    validated CSV + mapping -> per-asset parquet + registry
  GET  /onboarding/assets    registered plant assets with their mappings
  GET  /onboarding/health    partial-sensor health for the onboarded plant fleet
  POST /onboarding/assets/{id}/health recompute baseline-relative health + alert
  POST /onboarding/assets/{id}/score  gate + RUL inference (opt-in, 21 sensors)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sentinel.api.deps import require_api_key, service_dependency
from sentinel.api.schemas import (MappingProfileRequest, OnboardingImportRequest,
                                  OnboardingMappingRequest)
from sentinel.inference.service import SentinelService
from sentinel.onboarding.plant import inspect_frame, parse_csv, schema_payload, validate_csv
from sentinel.onboarding.service import (DriftBlocked, OnboardingBlocked, health_overview,
                                         import_csv, recompute_health, resolve_profile,
                                         score_asset)
from sentinel.store.db import (delete_mapping_profile, get_mapping_profile, get_plant_asset,
                               list_mapping_profiles, list_plant_assets, save_mapping_profile,
                               update_mapping_profile)

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
    mapping = payload.mapping
    drift = None
    if payload.profile_id is not None:
        try:
            mapping, drift = resolve_profile(payload.profile_id, payload.csv_text)
        except LookupError as exc:
            raise HTTPException(status_code=404,
                                detail=f"Unknown mapping profile {payload.profile_id}") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    if not mapping:
        raise HTTPException(status_code=422,
                            detail="Provide a mapping or a saved profile_id.")
    try:
        report = validate_csv(payload.csv_text, mapping,
                              source_file=payload.source_file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    report["drift"] = drift
    return report


@router.post("/onboarding/import", summary="Register validated plant assets",
             dependencies=[Depends(require_api_key)])
def import_assets(payload: OnboardingImportRequest) -> dict:
    _guard_size(payload.csv_text)
    if not payload.mapping and payload.profile_id is None:
        raise HTTPException(status_code=422, detail="Provide a mapping or a saved profile_id.")
    try:
        return import_csv(name=payload.name, text=payload.csv_text,
                          mapping=payload.mapping or {},
                          source_file=payload.source_file, notes=payload.notes,
                          profile_id=payload.profile_id, accept_drift=payload.accept_drift)
    except DriftBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OnboardingBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404,
                            detail=f"Unknown mapping profile {payload.profile_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc


@router.get("/onboarding/profiles", summary="Saved mapping profiles per source/vendor")
def profiles() -> dict:
    rows = list_mapping_profiles()
    return {
        "profiles": rows,
        "note": (
            "A profile stores the exact source-to-canonical mapping and the column set it was "
            "built from. Reusing it on a new export compares schemas and reports drift before "
            "any row is stored."
        ),
    }


@router.post("/onboarding/profiles", summary="Save a reusable mapping profile",
             dependencies=[Depends(require_api_key)])
def create_profile(payload: MappingProfileRequest) -> dict:
    try:
        return save_mapping_profile(name=payload.name, source=payload.source,
                                    mapping=payload.mapping,
                                    expected_columns=payload.expected_columns,
                                    notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/onboarding/profiles/{profile_id}", summary="One mapping profile")
def profile(profile_id: int) -> dict:
    record = get_mapping_profile(profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown mapping profile {profile_id}")
    return record


@router.put("/onboarding/profiles/{profile_id}", summary="Replace a mapping profile",
            dependencies=[Depends(require_api_key)])
def replace_profile(profile_id: int, payload: MappingProfileRequest) -> dict:
    record = update_mapping_profile(
        profile_id, name=payload.name, source=payload.source, mapping=payload.mapping,
        expected_columns=payload.expected_columns, notes=payload.notes,
    )
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown mapping profile {profile_id}")
    return record


@router.delete("/onboarding/profiles/{profile_id}", summary="Delete a mapping profile",
               dependencies=[Depends(require_api_key)])
def remove_profile(profile_id: int) -> dict:
    if not delete_mapping_profile(profile_id):
        raise HTTPException(status_code=404, detail=f"Unknown mapping profile {profile_id}")
    return {"deleted": True, "id": profile_id}


@router.post("/onboarding/profiles/{profile_id}/apply",
             summary="Compare a new export with a saved profile before importing")
async def apply_profile(profile_id: int, request: Request) -> dict:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 5 MB limit.")
    text = body.decode("utf-8-sig", errors="replace")
    try:
        mapping, drift = resolve_profile(profile_id, text)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown mapping profile {profile_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    return {"profile_id": profile_id, "mapping": mapping, "drift": drift}


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


@router.get("/onboarding/health",
            summary="Partial-sensor health for onboarded plant assets (not the C-MAPSS fleet)")
def plant_health() -> dict:
    return health_overview()


@router.post("/onboarding/assets/{registry_id}/health",
             summary="Recompute an asset's baseline-relative health and refresh its alert",
             dependencies=[Depends(require_api_key)])
def refresh_health(registry_id: int) -> dict:
    result = recompute_health(registry_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"Unknown plant asset {registry_id}")
    return result


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
