"""API dependencies."""

from __future__ import annotations

from fastapi import Header, HTTPException

from sentinel.config import settings
from sentinel.inference.service import SentinelService, get_service


def service_dependency() -> SentinelService:
    return get_service()


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional API-key guard for mutating endpoints.

    Disabled by default for local demonstrations; set SENTINEL_API_KEY to enable.
    """
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
