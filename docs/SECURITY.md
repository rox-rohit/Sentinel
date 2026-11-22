# Security and encryption

This document states what the platform protects, how, and what it deliberately
does not do. Nothing here is decorative: every control listed is implemented and
covered by a test or a runtime check.

## Threat model

| Asset | Risk | Control |
|---|---|---|
| Write endpoints (alerts, scenarios, profiles, onboarding, twins) | Anonymous mutation of operational data | `X-API-Key` (constant-time compare), optional fail-closed mode |
| Telemetry ingest | Spoofed machines or injected samples | Per-device `X-Device-Token`, PBKDF2 digest, rotation, per-device throttle |
| Console credentials | Token theft from disk or bundle | Device tokens session-only; operator key session-only; no secrets in the build |
| Service availability | Request floods, oversized bodies | Per-client rate limit, 8 MB body cap, 25 samples/s/device |
| Browser embedding | Clickjacking, MIME sniffing, referrer leakage | `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, frame-locked CSP |
| Data in transit | Eavesdropping on the public host | TLS terminated by App Service; HSTS emitted on HTTPS |
| Data at rest | Database or dump disclosure | Managed PostgreSQL storage encryption (AES-256); no reversible secrets stored |

## Credentials

**Operator key.** `SENTINEL_API_KEY` is read from the environment only. When it
is set, every mutating route requires `X-API-Key`; comparison uses
`hmac.compare_digest`. `SENTINEL_REQUIRE_API_KEY=true` makes the API fail closed
(503) if the key was never configured. Reads stay open so dashboards and the
snapshot fallback work.

**Device token.** `POST /api/v1/devices` returns `sntl_…` exactly once. The
database stores a 12-character display prefix, a 16-byte random salt and a
PBKDF2-SHA256 digest (120,000 iterations). Verification is constant time.
`POST /devices/{id}/rotate-token` replaces all three fields, so the previous
token stops working immediately. The token is never logged and never returned by
`GET`.

The console keeps tokens in `sessionStorage` (cleared when the tab closes) and
sends them only in `X-Device-Token`. It keeps the operator key in
`sessionStorage` too, entered in System Settings → Access control.

## Transport and headers

`HardeningMiddleware` runs before routing and adds, on every response:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()
Content-Security-Policy: frame-ancestors 'none'; object-src 'none'
Cross-Origin-Opener-Policy: same-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains   (HTTPS only)
```

The CSP intentionally does not set `default-src`, because `/docs` loads Swagger
UI assets from a CDN. It still prevents framing and plugin embedding.

CORS allows only the configured console origins and the verbs the console uses
(`GET, POST, PUT, PATCH, DELETE, OPTIONS`), with `Content-Type`, `X-API-Key` and
`X-Device-Token` as allowed headers.

## Limits

| Limit | Value | Where |
|---|---|---|
| Request body | 8 MB | `HardeningMiddleware` |
| Onboarding CSV | 5 MB | `routes/onboarding.py` |
| API rate | `SENTINEL_RATE_LIMIT_PER_MINUTE` (default 300) per client/route prefix | `HardeningMiddleware` |
| Device ingest | 25 samples/second/device | `routes/devices.py` |
| Twin channels | 64 per sample, finite values | `twins/service.py` |
| Live replay | 20–5000 ms pacing, 0.25–8× speed | `routes/replay.py` |

Rate limits are in-process. A multi-instance deployment needs a shared counter
(API gateway or Redis); the current App Service runs one uvicorn worker.

## Encryption

- **In transit:** HTTPS only on the hosted deployment. The API also honours
  `X-Forwarded-Proto` from App Service so HSTS is emitted on proxied TLS.
- **At rest:** PostgreSQL Flexible Server encrypts storage with service-managed
  AES-256 keys. Backups inherit the same encryption.
- **Secrets:** the database password lives only in App Service settings (and the
  GitHub repository secret for the publish profile / SWA token). Device tokens
  are one-way digests, so there is no plaintext secret to encrypt.
- **Not implemented:** application-level field encryption. It would require a
  key-management service and a compiled crypto dependency that is not installed;
  for one-way credentials it adds no protection. Add a KMS-backed encryptor
  before storing any reversible third-party secret.

## Deployment checklist

1. Set `SENTINEL_API_KEY` and `SENTINEL_REQUIRE_API_KEY=true` in App Service.
2. Enter the same key once in System Settings → Access control (session only).
3. Keep `SENTINEL_CORS_ORIGINS` limited to the console origin.
4. Rotate the App Service publishing profile and SWA token if either leaked.
5. Run one device registration per machine; store its token on the gateway, not
   in the repository.
6. Confirm `/api/v1/health` returns the security headers and that an anonymous
   `POST /devices/{id}/telemetry` returns 401.

## Non-goals

- Multi-tenant identity, SSO or role-based permissions. The console is a
  single-operator deployment; per-user attribution on alerts is an explicit
  string, not an authenticated identity.
- Intrusion detection, WAF rules or audit-log shipping. Those belong to the
  hosting platform (App Service / Front Door).
