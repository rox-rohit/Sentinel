"""API dependencies."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from sentinel.config import settings
from sentinel.inference.service import SentinelService, get_service


def service_dependency() -> SentinelService:
    return get_service()


def api_key_valid(candidate: str | None) -> bool:
    """True when the platform has no key (local mode) or the key matches."""
    if not settings.api_key:
        return not settings.require_api_key
    return bool(candidate) and hmac.compare_digest(candidate, settings.api_key)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Guard for mutating endpoints.

    A key is optional in local demonstrations. Set ``SENTINEL_API_KEY`` to
    require one, and ``SENTINEL_REQUIRE_API_KEY=true`` to fail closed even when
    the key was never configured.
    """
    if settings.require_api_key and not settings.api_key:
        raise HTTPException(
            status_code=503,
            detail="Mutations are disabled: SENTINEL_REQUIRE_API_KEY is set but no key is configured.",
        )
    if settings.api_key and not api_key_valid(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
