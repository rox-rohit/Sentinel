# API Documentation

Base URL: `http://127.0.0.1:8000/api/v1`
Interactive OpenAPI: `/docs` · ReDoc: `/redoc`

```bash
python -m uvicorn sentinel.api.main:app --port 8000
```

All errors use one envelope:

```json
{ "error": { "code": "http_404", "message": "Unknown asset FD001-999" } }
```

| Code | Meaning |
|---|---|
| 400 | Invalid request semantics (e.g. sequence too short) |
| 401 | API key required but missing/invalid |
| 404 | Unknown asset, dataset or model |
| 413 | Upload larger than 5 MB (onboarding) or 8 MB (global body cap) |
| 422 | Pydantic validation failure, or auto mode without a bound asset |
| 429 | Rate limit exceeded, or more than 25 samples/second for one device |
| 503 | Build artifacts missing — run the pipeline |

## System

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness, snapshot age, artifact readiness |
| GET | `/system/status` | Build metadata, artifact presence, dataset versions |
| POST | `/system/reload` | Reload snapshot artifacts after a rebuild (mutating) |

## Fleet

| Method | Path | Description |
|---|---|---|
| GET | `/fleet/summary` | KPIs, health distribution, risk bands, weights |
| GET | `/fleet/assets?status=&sort=` | Asset list (`sort=health\|risk\|rul\|id`) |
| GET | `/fleet/assets/{asset_id}` | Full asset, including telemetry series |
| GET | `/alerts?limit=&status=&asset_id=` | Alert inbox with lifecycle status and counts |
| GET | `/alerts/{id}` | Single alert with acknowledgement/resolution audit fields |
| POST | `/alerts/{id}/acknowledge` | Acknowledge an alert (`actor`, optional `note`); 409 if resolved |
| POST | `/alerts/{id}/resolve` | Resolve an alert (`actor`, optional `note`); 409 if already resolved |

## Prediction

| Method | Path | Description |
|---|---|---|
| POST | `/predict/failure` | Score one AI4I process record |
| POST | `/predict/failure/explain` | Local occlusion attribution for that record |
| POST | `/predict/rul` | RUL from a sequence of at least 30 cycles |
| GET | `/predictions` | Horizon curve, risk distribution, confidence, top risk |
| GET | `/rul` | Official benchmark, comparison, points, fleet estimates |
| GET | `/anomalies` | Severity distribution, histogram, recent alerts |
| GET | `/explainability` | Global importance, samples, calibration, failure modes |
| GET | `/forecast` | Sensor forecasting benchmark, best model per cell, example horizon window |

## Replay (recorded telemetry stream)

| Method | Path | Description |
|---|---|---|
| GET | `/replay/units` | Units available for replay, with cycle counts and fleet status |
| WS | `/ws/replay/{asset_id}?speed=&start_cycle=&interval_ms=` | Stream recorded cycles one frame at a time |

The stream replays rows from `artifacts/replay.parquet` produced by the build:
recorded C-MAPSS sensor readings plus the model estimates for that same cycle. It
is **simulated replay**, not a live sensor feed; no value is generated at request
time.

Client → server commands:

```json
{"action": "pause"}
{"action": "resume"}
{"action": "speed", "speed": 2}
{"action": "seek", "cycle": 120}
{"action": "restart"}
```

Server → client messages:

```json
{"type": "meta", "asset_id": "FD001-001", "total_cycles": 31,
 "sensors": [{"key": "s2", "label": "Fan inlet pressure (P2)"}],
 "source": "Recorded NASA C-MAPSS FD001 ...", "disclaimer": "Simulated replay ..."}

{"type": "frame", "seq": 12, "cycle": 12, "total_cycles": 31,
 "rul_estimate": 118.4, "rul_lower": 99.3, "rul_upper": 125.0,
 "risk_30": 0.0, "health": 97.1, "anomaly_score": 0.82,
 "anomaly_severity": "normal", "sensors": {"s2": 642.1, "s3": 1590.4}}

{"type": "state", "playing": false, "speed": 2, "cycle": 12, "total_cycles": 31}
{"type": "end", "cycle": 31, "total_cycles": 31}
{"type": "error", "code": "unknown_asset", "message": "..."}
```

`speed` is clamped to 0.25–8× and controls pacing only. `interval_ms` (20–5000)
overrides pacing for tests or slow clients. Unknown assets receive an `error`
message and close code `4404`. Frames are strict JSON: missing parquet values
become `null`, never `NaN`.

### Example — failure scoring

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/predict/failure \
  -H 'Content-Type: application/json' \
  -d '{"air_temp_k":302.5,"process_temp_k":312,"rotational_speed_rpm":1300,
       "torque_nm":65,"tool_wear_min":220,"product_type":"L"}'
```

```json
{
  "probability": 0.8134,
  "threshold": 0.28,
  "alert": true,
  "risk_band": "high",
  "model": "RandomForest",
  "dataset": "ai4i"
}
```

The same payload to `/predict/failure/explain` returns ranked contributions,
the reference medians used, and a narrative generated from those attributions.

### Example — RUL from a sequence

```json
{
  "readings": [
    { "cycle": 1, "s1": 518.67, "s2": 641.82, "...": "...", "s21": 23.4 }
  ]
}
```

Requires `op1..op3` optionally and all `s1..s21` channels; at least 30 cycles so
the 30-cycle rolling window is complete. Response includes the estimate, the
empirical interval and horizon risks.

## Digital twins

A twin binds a registered machine to a fleet asset. The asset's healthy cycles
define a per-channel median and robust scale; every ingested sample is scored
against it. See `docs/SECURITY.md` for the credential model.

| Method | Path | Description |
|---|---|---|
| GET | `/devices/schema` | Channel catalogue, ingest contract, scoring formula, limits |
| POST | `/devices` | Register a machine; returns the one-time `token` (mutating) |
| GET | `/devices` | Registered twins with latest state, trend and auto status |
| GET | `/devices/{device_id}` | Twin snapshot: state, history, baseline, model reference |
| PATCH | `/devices/{device_id}` | Rename, re-bind, change mode or interval (mutating) |
| DELETE | `/devices/{device_id}` | Remove the twin and its samples (mutating) |
| POST | `/devices/{device_id}/telemetry` | Ingest one sample (`X-Device-Token`) |
| POST | `/devices/{device_id}/auto/start` | Stream the bound asset's recorded cycles (mutating) |
| POST | `/devices/{device_id}/auto/stop` | Stop the auto feed (mutating) |
| POST | `/devices/{device_id}/rotate-token` | Issue a new ingest token (mutating) |

A gateway sends:

```http
POST /api/v1/devices/dev_1a2b3c4d5e6f/telemetry
Content-Type: application/json
X-Device-Token: sntl_…

{"sensors": {"s2": 642.1, "s3": 1589.4, "s7": 554.3}, "cycle": 42}
```

Response (trimmed):

```json
{"accepted": true, "sample": {"seq": 7, "health": 96.4},
 "twin": {"usable": true, "health_score": 96.4, "category": "healthy",
          "anomaly_score": 0.31, "severity": "normal",
          "coverage": {"expected": 8, "matched": 3, "coverage": 0.375,
                       "missing": ["s4", "s8"], "unknown": [], "rejected": []},
          "sensors": [{"sensor": "s2", "value": 642.1, "median": 640.7,
                       "z_score": 0.05, "deviation_pct": 0.22}],
          "explanation": "3 of 8 channels matched the baseline; …"}}
```

Scoring (deterministic, no model call):

```
deviation_index = 0.65 × max|z| + 0.35 × median|z|
health          = 100 − min(50, 11 × deviation_index) − 20 × (1 − coverage)
```

`coverage` is `matched / expected`; unknown channels are listed and excluded.
Auto mode is an ingest source: it steps the bound asset's recorded C-MAPSS
trajectory through the same endpoint logic at `interval_ms` (250–60000) and
stops at the end of the recording. It requires an artifact build and returns 422
without a bound asset.

## Decision

| Method | Path | Description |
|---|---|---|
| GET | `/maintenance?budget=` | Current plan, or re-optimised for a new budget |
| POST | `/maintenance/optimize` | Optimise with custom assets (`MaintenanceAsset[]`) |
| GET | `/maintenance/scenarios` | Saved optimisation scenarios (newest first) |
| POST | `/maintenance/scenarios` | Optimise at a budget and save it (`name`, `budget`, optional `note`) |
| GET | `/maintenance/scenarios/compare?ids=` | Side-by-side comparison of 2–6 saved scenarios |
| GET | `/maintenance/scenarios/{id}` | One saved scenario, including its full plan |
| DELETE | `/maintenance/scenarios/{id}` | Delete a saved scenario |
| GET | `/settings` | Cost model, health weights, thresholds |
| GET | `/drift` | PSI report for both datasets |

## Onboarding (real-plant CSV)

| Method | Path | Description |
|---|---|---|
| GET | `/onboarding/schema` | Canonical telemetry schema, aliases, required fields and limits |
| POST | `/onboarding/inspect?filename=` | Raw CSV body → columns, samples, suggested mapping, unmapped list |
| POST | `/onboarding/validate` | CSV + mapping → readiness, quality score, issues, scoring eligibility |
| POST | `/onboarding/import` | Validated CSV + mapping → per-asset parquet and registry rows (422 if blocked) |
| GET | `/onboarding/assets` | Registered plant assets with mapping, readiness, baseline and health |
| GET | `/onboarding/health` | Partial-sensor health, coverage confidence, thresholds and guidance |
| GET | `/onboarding/assets/{id}` | One registered asset |
| POST | `/onboarding/assets/{id}/health` | Recompute baseline-relative health and refresh the plant alert |
| POST | `/onboarding/assets/{id}/score` | Gated RUL inference; 422 with reasons if not eligible |
| GET | `/onboarding/profiles` | Saved mapping profiles with source, mapping and use count |
| POST | `/onboarding/profiles` | Save a profile (unique name; 409 on duplicate) |
| GET | `/onboarding/profiles/{id}` | One profile |
| PUT | `/onboarding/profiles/{id}` | Replace a profile |
| DELETE | `/onboarding/profiles/{id}` | Delete a profile |
| POST | `/onboarding/profiles/{id}/apply` | Raw CSV body → drift report and merged mapping, nothing stored |

Details: `docs/ONBOARDING.md`.

## Catalog

| Method | Path | Description |
|---|---|---|
| GET | `/datasets` | Registered dataset versions + quality reports |
| GET | `/datasets/{name}/quality` | Quality history for one dataset |
| GET | `/eda?dataset=cmapss\|ai4i` | Descriptive stats, correlations, degradation |
| GET | `/models` | Registry with metrics, version and status |
| GET | `/models/{name}` | Latest entry for a model |
| POST | `/datasets/upload?schema=&name=` | Validate and store a CSV/TXT body |

### Upload

Send the raw file body (`Content-Type: text/csv` or `text/plain`), maximum 5 MB:

```bash
curl -X POST \
  'http://127.0.0.1:8000/api/v1/datasets/upload?schema=ai4i&name=my-batch' \
  -H 'Content-Type: text/csv' --data-binary @batch.csv
```

The file is mapped to the canonical schema, validated, and stored as parquet
under `data/processed/uploads/`. **It does not trigger retraining**; promote a
dataset by running the build pipeline.

## Authentication

Two credentials exist:

* **Operator key** — set `SENTINEL_API_KEY`; mutating routes then require
  `X-API-Key` (compared in constant time). Reads stay open for dashboards.
  `SENTINEL_REQUIRE_API_KEY=true` fails closed when no key is configured.
* **Device token** — issued once by `POST /devices`, stored only as a PBKDF2
  digest. Required as `X-Device-Token` on telemetry ingest; a valid operator key
  is also accepted. Anonymous ingest returns 401.

Every response carries security headers (nosniff, frame denial, no-referrer,
permissions policy, frame-locked CSP; HSTS on HTTPS). API routes are rate
limited per client (`SENTINEL_RATE_LIMIT_PER_MINUTE`, default 300) and request
bodies above 8 MB are rejected before routing. CORS is restricted to the
configured console origins and to GET/POST/PUT/PATCH/DELETE/OPTIONS. No secret
is ever returned by the API except the one-time device token.

## Design notes

- Routers contain no model logic; they call `sentinel.inference.service`.
- Responses are computed from build artifacts; the only live model calls are the
  prediction endpoints.
- Missing artifacts return 503 with an actionable message instead of a stack trace.
