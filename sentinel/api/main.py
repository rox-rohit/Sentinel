"""SENTINEL API application.

Run locally:
    python -m uvicorn sentinel.api.main:app --port 8000
OpenAPI docs: http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sentinel import __version__
from sentinel.api.routes import ROUTERS
from sentinel.config import settings
from sentinel.inference.service import ArtifactUnavailable
from sentinel.logging_setup import get_logger
from sentinel.store.db import init_db

log = get_logger("api")

app = FastAPI(
    title="SENTINEL API",
    version=__version__,
    description=(
        "Industrial intelligence and predictive maintenance API. Predictions come from "
        "models trained on NASA C-MAPSS and UCI AI4I 2020 by "
        "`python -m sentinel.pipelines.build`."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    # Development servers may pick another loopback port when 5173 is busy;
    # hosted deployments add their exact origin via SENTINEL_CORS_ORIGINS.
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.exception_handler(ArtifactUnavailable)
async def artifact_unavailable(_: Request, exc: ArtifactUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "artifacts_unavailable", "message": str(exc)}},
    )


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": str(exc)}},
    )


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": f"http_{exc.status_code}", "message": detail}},
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Unexpected server error."}},
    )


for router in ROUTERS:
    app.include_router(router, prefix=settings.api_prefix)


@app.on_event("startup")
def init_store() -> None:
    """Prepare the operational store before the first request is served."""
    init_db()


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "product": "SENTINEL",
        "version": __version__,
        "api": settings.api_prefix,
        "docs": "/docs",
    }
