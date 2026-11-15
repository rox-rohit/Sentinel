# SENTINEL — Task Board

Updated: 2026-11-15 (Phase 0–3, 5 foundation; Phase 6 replay streaming)

## ✅ Completed and verified

### Phase 0
- [x] Inspect repository, environment, GPU, dependencies, disk.
- [x] Fetch C-MAPSS (Zenodo / NASA PCoE mirror) and AI4I 2020 (UCI) into `data/raw`.
- [x] Write vision, roadmap, decisions, architecture, persistent instructions.

### Phase 1 — Foundation
- [x] `sentinel` package, typed `Settings`, structured logging.
- [x] Dataset adapter interface + registry + canonical schema.
- [x] Validation engine and quality reports.
- [x] SQLAlchemy store (datasets, model versions, alerts).
- [x] FastAPI `/api/v1` application: health, datasets, fleet, assets,
      predictions, RUL, anomalies, explainability, maintenance, models, EDA,
      drift, system status.
- [x] Frontend design tokens, primitives, layout shell, sidebar, top bar, router.
- [x] Fleet Overview with real artifact snapshot.

### Phase 2 — Data foundation
- [x] AI4I adapter (10,000 rows, 5 labelled failure modes).
- [x] C-MAPSS adapter (FD001–FD004, 26-column raw format, unit/cycle aware).
- [x] Schema/type/duplicate/outlier/constant-channel validation.
- [x] Parquet processed datasets with version metadata.
- [x] EDA pipeline: descriptive stats, skew, correlation matrix, degradation
      trend, missingness, failure balance, machine comparison.
- [x] Feature engineering: rolling mean/std/min/max, EMA, deltas, lag, leakage
      guard, feature specification and versioning.

### Phase 3 — Classical ML
- [x] Failure classification comparison (LR, RF, ExtraTrees, HistGB, XGBoost),
      stratified CV, class weights, PR-AUC/ROC-AUC/F1/recall/precision,
      confusion matrix, FPR/FNR, expected cost, threshold optimisation.
- [x] Multi-label failure-mode classification on real AI4I labels.
- [x] RUL regression (Ridge, RF, XGBoost), engine-wise split, NASA score,
      uncertainty quantiles, horizon risk.
- [x] Model artifact persistence + registry records.
- [x] Snapshot export consumed by the UI.

### Phase 5 — Decision intelligence
- [x] Transparent health score with categories and published weights.
- [x] Maintenance prioritisation and budget-constrained knapsack selection.
- [x] Reactive vs preventive vs predictive cost scenarios.

### Phase 6 — Replay streaming
- [x] Build exports `artifacts/replay.parquet`: every recorded test cycle with
      its RUL, band, risk, anomaly score/severity and health.
- [x] `sentinel/replay` service + `ReplayPlayer` cursor (pause, resume, speed,
      seek, restart); pacing never changes data.
- [x] `GET /api/v1/replay/units` and `WS /api/v1/ws/replay/{asset_id}` with a
      typed message protocol (`meta`, `frame`, `state`, `end`, `error`).
- [x] Live Monitoring page: unit picker, play/pause, 0.5–4× speed, progress,
      live stats, RUL/health charts, sensor telemetry and an event log.
- [x] Explicit "Simulated replay" labelling; local artifact fallback when the
      API is offline (RUL bands and severity marked unavailable there).
- [x] NaN/Infinity normalised to null so browsers can parse every frame.

### Verification
- [x] `python -m pytest -q` — 30 passed (data, validation, features, metrics,
      decisions, API integration, RUL sequence inference, replay cursor and
      WebSocket protocol, strict-JSON frame safety).
- [x] `bun run typecheck` — clean.
- [x] `bun run build` — Vite + Worker build, dist/sentinel/index.js produced.
- [x] `bun test tests` — worker health/404 behaviour.

## 🟡 In progress / partial
- [ ] Model registry promotion workflow in the UI (metadata + status exist).
- [ ] Drift report surfaced on the Model Lab page (API exists).
- [ ] Alert lifecycle (generated + listed; no acknowledgement endpoint yet).

## ⬜ Pending — next tasks, in order
1. **Phase 4** — forecasting module: moving-average/ETS baselines, gradient
   boosting, chronological validation, MAE/RMSE/MASE.
2. **Phase 4** — deep learning lab once disk/CUDA allow (DECISIONS D-008):
   sequence tensors, LSTM/GRU/1D-CNN/Transformer, early stopping, checkpoints.
3. **Phase 7** — forecasting page, scenario comparison persistence,
   alert acknowledgement.
4. **Phase 6** — MLflow tracking + retraining workflow with promotion policy.
5. **Phase 8** — architecture diagram, screenshots, technical report, video script.

## Known limitations
- Local metadata store is SQLite (`SENTINEL_DATABASE_URL` switches to PostgreSQL).
- Deep learning and MLflow are not installed (disk / Python 3.15 wheel limits).
- IMS Bearing dataset not integrated (not downloaded; needs signal-processing path).
- Snapshot fallback is static: no live inference when the API is unreachable.
  Live Monitoring degrades to an artifact replay without RUL bands/severity.
- Replay is recorded C-MAPSS data; there is no MQTT/OPC-UA/PLC ingestion.
