# SENTINEL — Task Board

Updated: 2026-11-17 (Phase 0–7; Phase 6 replay streaming; alert lifecycle)

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

### Phase 4 — Sensor forecasting
- [x] Causal lag/rolling/EMA features per sensor, shifted so cycle t never
      contributes to its own feature vector.
- [x] Persistence, moving-average, exponential-smoothing baselines and a
      gradient-boosted model on a change-from-current target (trees cannot
      extrapolate sensor levels).
- [x] Chronological validation per engine (first 70% train, remaining 30% test)
      with MAE, RMSE and MASE; no shuffling and no future windows.
- [x] Build artifact, registry entry (`cmapss_sensor_forecast`), `GET /forecast`
      and a Forecasting page with the sensor × horizon comparison table and an
      example forecast against recorded actuals.
- [x] Result: exponential smoothing wins all 12 reported cells (mean MASE
      0.881 vs persistence 1.061, 17% better); gradient boosting underperforms
      on the held-out tail. Recorded as an honest negative result.

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

### Phase 7 — Alert lifecycle
- [x] Deterministic alert fingerprint (asset + kind + cycle): a rebuild refreshes
      severity/message/score but keeps acknowledgement and resolution state.
- [x] Store migration adds `fingerprint`, `status`, actor/timestamp and note
      columns to existing SQLite databases; no manual reset needed.
- [x] `sync_alerts` inserts new alerts, updates existing ones and deletes only
      still-open alerts that the pipeline no longer produces; acknowledged and
      resolved alerts remain as an audit trail.
- [x] `GET /alerts?status=&asset_id=&limit=` returns records plus counts per
      status; `GET /alerts/{id}` returns a single alert.
- [x] `POST /alerts/{id}/acknowledge` and `POST /alerts/{id}/resolve` record the
      actor, timestamp and optional note; resolving twice or acknowledging a
      resolved alert returns 409, unknown ids 404.
- [x] Anomaly Centre "Alert inbox" with status filters, counts and Ack/Resolve
      controls; falls back to the read-only snapshot list when the API is down.

### Phase 7 — Saved maintenance scenarios
- [x] `maintenance_scenarios` table persists the complete optimisation plan
      (selection, strategy costs, assumptions) with name, note, budget and
      summary columns; saved plans survive fleet rebuilds unchanged.
- [x] `POST /maintenance/scenarios` optimises at the requested budget and saves
      the result; `GET /maintenance/scenarios` lists summaries;
      `GET /maintenance/scenarios/{id}` returns the full plan;
      `DELETE /maintenance/scenarios/{id}` removes one.
- [x] `GET /maintenance/scenarios/compare?ids=` compares 2–6 scenarios on
      avoided loss, predictive cost, spend, downtime, assets serviced and
      avoided loss per 1,000 spent; each metric marks its best value, and asset
      overlap (shared/distinct) is reported. Unknown ids return 404, fewer than
      two ids 422.
- [x] Maintenance Optimiser "Saved scenarios" panel: name and save the current
      plan, select up to four, compare side by side with best-value highlighting,
      and delete; offline mode explains that persistence needs the API.

### Real-plant onboarding (prototype)
- [x] Canonical `plant-telemetry-v1` schema: asset_id + cycle required, op1–op3
      and s1–s21 optional; documented in `docs/ONBOARDING.md`.
- [x] Column-mapping inspection with alias/sensor-pattern suggestions and
      confidence; ambiguous C-MAPSS labels (Ps30, NRf, NRc) intentionally not
      auto-mapped.
- [x] Validation gate before storage or inference: required fields, duplicate
      targets/keys, non-numeric values, missingness, cycle gaps, negative values,
      short history and ordering; readiness + quality score + per-field issues.
- [x] `plant_assets` registry with one parquet per asset, exact mapping stored
      per asset, upsert on canonical asset id, readiness and score eligibility.
- [x] Scoring gate: 422 with explicit reasons unless validated, all 21 sensors
      mapped and at least 30 cycles; successful scores carry an
      out-of-distribution warning.
- [x] Data Onboarding page: file/paste, mapping table, validation report,
      register action, registry with mapping preview and gated scoring.

### Verification
- [x] `python -m pytest -q` — 59 passed (data, validation, features, metrics,
      decisions, API integration, RUL sequence inference, replay cursor and
      WebSocket protocol, strict-JSON frame safety, chronological forecasting,
      alert identity/persistence/transitions, scenario persistence/comparison,
      onboarding mapping/validation/registry/scoring gate).
- [x] `bun run typecheck` — clean.
- [x] `bun run build` — Vite + Worker build, dist/sentinel/index.js produced.
- [x] `bun test tests` — worker health/404 behaviour.

## 🟡 In progress / partial
- [ ] Model registry promotion workflow in the UI (metadata + status exist).
- [ ] Drift report surfaced on the Model Lab page (API exists).


### Phase 8 — Portfolio release
- [x] Technical report (`docs/TECHNICAL_REPORT.md`): architecture, modelling
      decisions with negative results, evaluation evidence, limitations,
      reproducibility and future work.
- [x] Demo narrative and timed three-minute walkthrough
      (`docs/DEMO_SCRIPT.md`), including snapshot-mode fallback and expected Q&A.
- [ ] Architecture diagram asset (SVG/PNG) for the README.
- [ ] Recorded demo video from the script.

## ⬜ Pending — next tasks, in order
1. **Phase 4** — deep learning lab once disk/CUDA allow (DECISIONS D-008):
   sequence tensors, LSTM/GRU/1D-CNN/Transformer, early stopping, checkpoints.
2. **Onboarding** — OPC-UA/MQTT connector reusing the same validation contract;
   timestamp parsing and unit conversion; retained asset versions.
3. **Phase 6** — MLflow tracking + retraining workflow with promotion policy.

## Known limitations
- Local metadata store is SQLite (`SENTINEL_DATABASE_URL` switches to PostgreSQL).
- Deep learning and MLflow are not installed (disk / Python 3.15 wheel limits).
- IMS Bearing dataset not integrated (not downloaded; needs signal-processing path).
- Snapshot fallback is static: no live inference when the API is unreachable.
  Live Monitoring degrades to an artifact replay without RUL bands/severity.
- Replay is recorded C-MAPSS data; there is no MQTT/OPC-UA/PLC ingestion.
