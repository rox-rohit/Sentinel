# SENTINEL — Development Roadmap

Status legend: ✅ done & verified · 🟡 partial · ⬜ pending

## Phase 0 — Inspection & planning ✅

Repository inspected (existing Freebuff Vite/React starter, no Python app).
Environment verified: Python 3.15.0, Node 24, RTX 3050 4 GB, ~3.5 GB free disk,
no CUDA PyTorch. Datasets fetched from primary sources. Vision, architecture,
decisions, task list and methodology docs written.

Deliverables: `PROJECT_VISION.md`, `SYSTEM_ARCHITECTURE.md`,
`DEVELOPMENT_ROADMAP.md`, `TASKS.md`, `DECISIONS.md`, `docs/*`, `AGENTS.md`.

## Phase 1 — Foundation ✅

- Python package skeleton with typed config and structured logging.
- Dataset adapter registry + canonical schema mapping.
- Validation engine with data-quality reports.
- SQLAlchemy metadata store (SQLite locally, PostgreSQL via env var).
- FastAPI app with versioned routers, Pydantic schemas, error envelope,
  health checks, CORS for the local UI.
- Frontend design system (tokens, primitives, charts), application shell,
  sidebar navigation, top bar, routing.
- Fleet Overview consuming the exported artifact snapshot / live API.
- Verification: 22 pytest tests, `bun run typecheck`, `bun run build`.

## Phase 2 — Data foundation ✅

- AI4I 2020 and C-MAPSS FD001–FD004 ingestion through adapters.
- Schema/dtype/duplicate/outlier/constant-channel validation and quality reports.
- Parquet processed outputs + dataset version records.
- EDA generated from the active dataset (distributions, correlations, trends,
  missingness, failure balance, machine comparison).
- Leakage-safe feature engineering with recorded feature specifications.

## Phase 3 — Classical machine learning ✅

- Failure classification: Logistic Regression, Random Forest, Extra Trees,
  Histogram Gradient Boosting, XGBoost; stratified CV, class-imbalance
  handling, probability threshold optimisation under an explicit cost model.
- Metrics: precision, recall, F1, ROC-AUC, PR-AUC, confusion matrix, FPR, FNR,
  expected cost — accuracy never used alone.
- Failure-mode multi-label classification on AI4I's real TWF/HDF/PWF/OSF/RNF labels.
- RUL regression on C-MAPSS: Ridge, Random Forest, XGBoost; engine-wise split;
  RUL clipping documented; MAE, RMSE, NASA asymmetric score; residual-based
  uncertainty band and horizon risk.

## Phase 4 — Advanced ML 🟡

- ✅ IsolationForest / LOF / PCA-reconstruction anomaly ensemble, severity logic,
  affected-sensor attribution.
- ✅ XGBoost exact SHAP contributions + permutation importance.
- ⬜ Deep learning (LSTM/GRU/1D-CNN/Transformer) — blocked by disk/CUDA
  environment (DECISIONS D-008); classical baselines already recorded.
- ✅ Sensor forecasting: persistence / moving-average / exponential-smoothing
  baselines plus gradient boosting, chronological per-engine validation
  (70/30) and MAE/RMSE/MASE. Exponential smoothing wins; documented negative
  result for the boosted model on held-out tails.

## Phase 5 — Decision intelligence ✅

- Transparent 0–100 health score with published weights and category thresholds.
- Horizon failure risk derived from RUL residual distribution.
- Maintenance optimiser: priority under criticality/cost, budget-constrained
  selection (dynamic programming knapsack), reactive vs preventive vs predictive
  scenario costing with explicit assumptions.

## Phase 6 — Live simulation & MLOps 🟡

- ✅ Replay streaming: recorded C-MAPSS cycles exported by the build, served
  over `WS /api/v1/ws/replay/{asset_id}` with pause/resume/speed/seek/restart.
  Labelled simulated; no value is generated at request time.
- ✅ Live Monitoring page with unit picker, pacing controls, live RUL/health/
  anomaly readouts, telemetry charts and a threshold event log.
- ✅ Model registry: versions, metrics, active/candidate status, rollback-ready
  metadata; dataset registry; PSI feature/prediction drift report.
- ⬜ MLflow tracking server integration (disk-constrained; registry contract
  already compatible).
- ⬜ Retraining workflow with promotion policy.

## Phase 7 — Product integration 🟡

- ✅ Fleet Overview, Live Monitoring, Machine Intelligence, Digital Twin detail, Predictive
  Analytics, Anomaly Centre, RUL Intelligence, Explainability, Maintenance
  Optimiser, Model Laboratory, Dataset Management, Historical Analytics, Settings.
- ✅ Forecasting page (sensor × horizon MASE table, example forecast).
- ✅ Alert lifecycle: stable fingerprints, acknowledgement/resolution stored in
  the metadata database with actor, timestamp and note, and an Alert inbox with
  status filters and Ack/Resolve controls on the Anomaly Centre. State survives
  rebuilds; only still-open alerts the pipeline no longer generates are pruned.
- ⬜ Saved maintenance scenario comparison.

Verification for every page: it reads only fields that exist in the snapshot /
API contract; the UI labels live vs artifact-snapshot mode in the top bar.

## Phase 8 — Portfolio release ⬜

- Architecture diagram, screenshots, demo dataset narrative, technical report,
  model comparison report, setup documentation, demo video script.

## Next recommended task

Phase 7's saved scenario comparison, then MLflow tracking.
See `TASKS.md` for the granular list.
