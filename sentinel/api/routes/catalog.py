"""Catalog routes: datasets, EDA, model registry, dataset upload/validation."""

from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from sentinel.api.deps import require_api_key, service_dependency
from sentinel.config import DATA_PROCESSED, settings
from sentinel.data.adapters import load_adapter
from sentinel.data.adapters.cmapss import RAW_COLUMNS
from sentinel.data.preprocessing import frame_version
from sentinel.data.validation import validate_dataset
from sentinel.inference.service import SentinelService
from sentinel.store.db import DatasetRecord, list_datasets, list_models, session_scope

router = APIRouter(tags=["catalog"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
DATASET_CHOICES = {"ai4i", "cmapss"}


@router.get("/datasets", summary="Registered dataset versions and quality reports")
def datasets() -> dict:
    return {"datasets": list_datasets()}


@router.get("/datasets/{name}/quality", summary="Quality report for a dataset")
def dataset_quality(name: str) -> dict:
    records = [d for d in list_datasets() if d["name"] == name]
    if not records:
        raise HTTPException(status_code=404, detail=f"No registered dataset {name!r}")
    return {"dataset": name, "versions": records}


@router.get("/eda", summary="EDA generated from the processed datasets")
def eda(dataset: str = Query("cmapss", pattern="^(cmapss|ai4i)$"),
        service: SentinelService = Depends(service_dependency)) -> dict:
    payload = service.snapshot()["eda"].get(dataset)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No EDA for {dataset}")
    return payload


@router.get("/models", summary="Model registry with metrics and status")
def models() -> dict:
    return {"models": list_models()}


@router.get("/models/{name}", summary="Single model entry")
def model(name: str) -> dict:
    rows = [m for m in list_models() if m["name"] == name]
    if not rows:
        raise HTTPException(status_code=404, detail=f"No model {name!r}")
    return rows[0]


@router.post("/datasets/upload", summary="Upload and validate a CSV dataset",
             dependencies=[Depends(require_api_key)])
async def upload(request: Request, schema: str = Query("ai4i"),
                 name: str = Query("upload")) -> dict:
    if schema not in DATASET_CHOICES:
        raise HTTPException(status_code=422, detail=f"schema must be one of {sorted(DATASET_CHOICES)}")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 5 MB limit.")
    text = body.decode("utf-8-sig", errors="replace")
    try:
        raw = (
            pd.read_csv(io.StringIO(text))
            if schema == "ai4i"
            else pd.read_csv(io.StringIO(text), sep=r"\s+", header=None, names=RAW_COLUMNS)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc

    adapter = load_adapter(schema)
    try:
        canonical = adapter.canonicalize(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Schema validation failed: {exc}") from exc

    report = validate_dataset(canonical, adapter.schema)
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-") or "upload"
    folder = DATA_PROCESSED / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug}-{frame_version(canonical)}.parquet"
    canonical.to_parquet(path, index=False)

    with session_scope() as session:
        session.add(DatasetRecord(
            name=f"{schema}_upload",
            display_name=f"Uploaded {schema.upper()} dataset ({slug})",
            version=frame_version(canonical),
            rows=int(len(canonical)),
            columns=int(canonical.shape[1]),
            path=str(path),
            quality_json=json.dumps(report.to_dict(), default=str),
            schema_json=json.dumps(adapter.schema.to_dict(), default=str),
            source_url="user_upload",
        ))
    return {
        "accepted": report.ok,
        "rows": int(len(canonical)),
        "columns": int(canonical.shape[1]),
        "saved_to": str(path),
        "quality": report.to_dict(),
        "note": (
            "Uploads are validated and stored but do not retrain models automatically. "
            "Run the build pipeline after promoting a dataset."
        ),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
