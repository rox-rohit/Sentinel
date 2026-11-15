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
| 413 | Upload larger than 5 MB |
| 422 | Pydantic validation failure |
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
| GET | `/alerts?limit=` | Generated alerts from the metadata store |

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

## Decision

| Method | Path | Description |
|---|---|---|
| GET | `/maintenance?budget=` | Current plan, or re-optimised for a new budget |
| POST | `/maintenance/optimize` | Optimise with custom assets (`MaintenanceAsset[]`) |
| GET | `/settings` | Cost model, health weights, thresholds |
| GET | `/drift` | PSI report for both datasets |

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

Authentication is an optional dependency: set `SENTINEL_API_KEY` and mutating
routes require `X-API-Key`. Reads stay open for local dashboards. CORS is
restricted to the configured UI origins. No secret is ever returned by the API.

## Design notes

- Routers contain no model logic; they call `sentinel.inference.service`.
- Responses are computed from build artifacts; the only live model calls are the
  prediction endpoints.
- Missing artifacts return 503 with an actionable message instead of a stack trace.
