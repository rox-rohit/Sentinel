# SENTINEL — System Architecture

## 1. Layers

```
┌───────────────────────────────────────────────────────────────────────┐
│ Frontend — Vite + React 19 + TypeScript + Tailwind 4 + Recharts       │
│ pages → data layer (src/lib/api.ts) → snapshot fallback               │
└───────────────────────────────┬───────────────────────────────────────┘
                                │ HTTP /api/v1 (CORS, pydantic schemas)
┌───────────────────────────────▼───────────────────────────────────────┐
│ API — FastAPI, versioned routers, error envelope, OpenAPI /docs       │
│ routes → inference services → artifacts (no model code in routes)     │
└───────────────────────────────┬───────────────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────────────┐
│ Intelligence layer                                                     │
│  inference/  model loading, fleet assembly, risk, explanations         │
│  replay/     recorded-trajectory cursor and WebSocket frame source      │
│  decision/   health scoring, budget-constrained maintenance planner    │
│  models/     training, evaluation, anomaly, RUL, artifact store        │
│  features/   leakage-safe rolling/lag/EMA pipeline                     │
│  eda/        dataset-driven statistics and chart payloads              │
└───────────────────────────────┬───────────────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────────────┐
│ Data layer                                                             │
│  adapters (AI4I, C-MAPSS) → canonical frames → validation → parquet    │
│  raw CSV/TXT in data/raw · processed parquet in data/processed         │
│  SQLAlchemy metadata store (SQLite locally, PostgreSQL via env)        │
└───────────────────────────────────────────────────────────────────────┘
```

## 2. Runtime topology

| Component | Command | Port |
|-----------|---------|------|
| API | `python -m uvicorn sentinel.api.main:app --port 8000` | 8000 |
| UI | `bun run dev` | 5173 |
| Replay stream | `WS /api/v1/ws/replay/{asset_id}` (same API process) | 8000 |
| Static/Worker build | `bun run build` | — |

The UI resolves the API base URL from `VITE_API_BASE_URL` (default
`http://127.0.0.1:8000/api/v1`). If a request fails, it serves the exported
artifact snapshot and marks the data source as `snapshot` in the top bar.

## 3. Offline pipeline

`python -m sentinel.pipelines.build` runs, in order:

1. `load_adapter("cmapss"|"ai4i").load_raw()` — raw file discovery.
2. Validation → quality report (blocking on schema errors, warnings otherwise).
3. Preprocessing → processed parquet + dataset version row.
4. Feature engineering → feature frame + feature spec JSON.
5. Training:
   - RUL regression on C-MAPSS with engine-wise split.
   - Failure classifier comparison on AI4I with stratified split.
   - Failure-mode multi-label models.
   - Anomaly detectors fitted on early-life windows.
   - Explainability artifacts (SHAP global importance, permutation importance).
6. Evaluation reports + model cards written to `artifacts/` and the registry.
7. Platform assembly: per-asset RUL/risk/health/anomaly/alerts, maintenance plan
   under the configured budget, drift report, EDA payload.
8. Snapshot export → `artifacts/snapshot.json` and `src/generated/snapshot.json`.
9. Replay export → `artifacts/replay.parquet` (per-cycle recorded sensors plus
   RUL, band, risk, anomaly and health) for the Live Monitoring stream.

## 4. Module boundaries

- `sentinel/api/*` may import inference/decision/store. It must not call
  scikit-learn or XGBoost directly.
- `sentinel/inference/*` owns model loading and prediction; it never returns
  HTTP-specific objects.
- `sentinel/models/*` owns training, evaluation and serialization; it never
  knows about the API or UI.
- `sentinel/data/*` owns dataset-specific I/O and validation; it never knows
  about models.
- `sentinel/features/*` is dataset-agnostic: it receives canonical sensor frames.
- `sentinel/replay/*` owns frame construction and cursor semantics only; it
  emits plain dictionaries and has no HTTP or asyncio dependency, so pausing and
  ordering are unit-testable. The route adds pacing and JSON transport.

## 5. Extension points

- **New dataset** → subclass `DatasetAdapter`, register in
  `sentinel/data/adapters/registry.py`, add its canonical sensor mapping.
- **New model** → implement `ModelAdapter` (`fit`/`predict`/`card`) and register
  it in the comparison list for its task; the UI reads registry records, so no
  page changes are needed.
- **New decision rule** → extend `sentinel/decision/`; the API contract returns
  the same `MaintenancePlan` shape.

## 6. Reliability and error handling

- All API errors return `{ "error": { "code", "message" } }`.
- Missing artifacts produce `503` with a clear message, never a stack trace.
- Validation failures are collected, not raised one at a time.
- Logging is structured (`sentinel.logging_setup`) and includes request paths.

## 7. Security posture

- No secrets, dataset files or model binaries in version control.
- CORS restricted to configured origins (localhost by default).
- Upload endpoints validate extension, size and schema before writing.
- Authentication is designed as a dependency (`require_api_key`) that is disabled
  by default for local demos; enabling it requires `SENTINEL_API_KEY`.
