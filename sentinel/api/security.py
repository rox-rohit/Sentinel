"""Transport hardening middleware.

Applied to every HTTP request before routing:

* security headers (nosniff, frame denial, no-referrer, permissions policy,
  HSTS on HTTPS, and a conservative CSP that still allows the OpenAPI docs);
* a per-client sliding-window rate limit with a JSON error envelope;
* a global request-body cap in front of the per-route upload checks.

Rate limits are in-process. A multi-instance deployment needs a shared counter
(API gateway or Redis); the limit here still bounds a single worker.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sentinel.config import settings

RATE_LIMIT_WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 4096
BODY_LIMIT_BYTES = 8 * 1024 * 1024


def _client_key(scope: Scope) -> str:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-for")
    if forwarded:
        # Azure App Service terminates TLS and appends the real client first.
        return forwarded.decode("latin-1").split(",")[0].strip() or "unknown"
    client = scope.get("client")
    return (client[0] if client else "unknown") or "unknown"


def _route_bucket(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    return "/".join(parts[:3])


class HardeningMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        headers = dict(scope.get("headers") or [])

        length = headers.get(b"content-length")
        if length:
            try:
                if int(length) > BODY_LIMIT_BYTES:
                    await _json_response(send, 413, "request_too_large",
                                         "Request body exceeds the 8 MB limit.")
                    return
            except ValueError:
                await _json_response(send, 400, "bad_length", "Invalid Content-Length.")
                return

        if method != "OPTIONS" and path.startswith(f"{settings.api_prefix}/") \
                and path != f"{settings.api_prefix}/health":
            retry_after = self._limited(_client_key(scope), method, path)
            if retry_after is not None:
                await _json_response(
                    send, 429, "rate_limited",
                    "Too many requests; retry after the window resets.",
                    extra_headers=[(b"retry-after", str(retry_after).encode())],
                )
                return

        forwarded_proto = headers.get(b"x-forwarded-proto", b"").decode("latin-1")
        https = forwarded_proto == "https" or scope.get("scheme") == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                target = MutableHeaders(scope=message)
                target.setdefault("X-Content-Type-Options", "nosniff")
                target.setdefault("X-Frame-Options", "DENY")
                target.setdefault("Referrer-Policy", "no-referrer")
                target.setdefault(
                    "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
                )
                target.setdefault(
                    "Content-Security-Policy", "frame-ancestors 'none'; object-src 'none'"
                )
                target.setdefault("Cross-Origin-Opener-Policy", "same-origin")
                if https:
                    target.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _limited(self, client: str, method: str, path: str) -> int | None:
        limit = settings.rate_limit_per_minute
        if limit <= 0:
            return None
        now = time.monotonic()
        bucket = f"{client}|{method}|{_route_bucket(path)}"
        window = self._hits[bucket]
        while window and now - window[0] > RATE_LIMIT_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= limit:
            return max(1, int(RATE_LIMIT_WINDOW_SECONDS - (now - window[0])))
        window.append(now)
        if len(self._hits) > MAX_TRACKED_CLIENTS:
            for key in list(self._hits)[: MAX_TRACKED_CLIENTS // 2]:
                self._hits.pop(key, None)
        return None


async def _json_response(send: Send, status: int, code: str, message: str,
                         extra_headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"x-content-type-options", b"nosniff"),
    ]
    headers.extend(extra_headers or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
