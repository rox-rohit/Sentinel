# SENTINEL — Product Vision

**Industrial Intelligence & Predictive Maintenance Platform**

> Predict Failure. Understand Risk. Optimize Operations.

## 1. Problem

Industrial maintenance teams make high-stakes decisions from fragmented signals:
vibration alarms, temperature excursions, tool-wear counters, operator intuition
and spreadsheets. Unplanned downtime is expensive, while over-maintenance burns
labour and parts. Most "predictive maintenance dashboards" stop at a risk score
and leave the hard part — *what should we do, on which machine, this week, within
this budget?* — to the human.

SENTINEL closes that loop: telemetry → validated data → models → explanations →
asset health → prioritized, budget-constrained maintenance plans.

## 2. The six questions

1. **What is happening?** — sensor telemetry, operating conditions, degradation history.
2. **Is it normal?** — unsupervised anomaly detection with severity and affected sensors.
3. **Is it likely to fail?** — supervised failure classification and horizon risk.
4. **When?** — Remaining Useful Life regression with validated uncertainty.
5. **Why?** — SHAP attributions, permutation importance, degradation evidence.
6. **What next?** — maintenance prioritisation under cost, downtime and budget constraints.

## 3. Users

Maintenance engineers, reliability engineers, plant managers, operators and
industrial analytics teams. The interface is an operations command centre: dense,
dark, calm, and readable at a glance on a control-room display.

## 4. Product principles

- **Evidence over decoration.** Every number in the UI is produced by
  `sentinel.pipelines.build` from a real dataset, a real trained model, or is
  labelled as a demonstration fixture.
- **Honest uncertainty.** RUL is a distribution-aware estimate, not a failure date.
- **Attribution ≠ causation.** SHAP explains model behaviour, not physics.
- **Reproducibility.** Fixed seeds, versioned datasets, recorded metrics and
  configs. Every reported number can be regenerated with one command.
- **Modularity.** Dataset adapters and model adapters are registries; new
  datasets/models integrate without touching the UI or the API contract.
- **No fabricated labels.** Failure-mode prediction is only exposed for modes the
  training data actually labels.

## 5. Scope — implemented foundations and target modules

| # | Module | State |
|---|--------|-------|
| 1 | Data engineering & ingestion (adapters, validation, quality reports, versioning) | implemented |
| 2 | Exploratory data analysis generated from the dataset | implemented |
| 3 | Feature engineering (rolling/lag/EMA/deltas, leakage guards, feature specs) | implemented |
| 4 | Failure prediction (classical ML comparison, threshold & cost optimisation) | implemented |
| 5 | Failure-mode classification (AI4I multi-label, real labels only) | implemented |
| 6 | RUL prediction (Ridge / RandomForest / XGBoost, NASA score, uncertainty) | implemented (classical); deep sequence models deferred |
| 7 | Anomaly detection (IsolationForest, LOF, PCA reconstruction) | implemented |
| 8 | Time-series forecasting | planned (Phase 4) |
| 9 | Deep learning laboratory (LSTM/GRU/CNN/Transformer, PyTorch) | planned — environment blocked, see DECISIONS D-008 |
| 10 | Explainable AI (XGBoost exact SHAP contributions, permutation importance) | implemented |
| 11 | Machine health scoring (transparent, configurable) | implemented |
| 12 | Decision intelligence & maintenance optimisation (budget-constrained) | implemented |
| 13 | Simulated live monitoring (replay API/WebSocket) | implemented — recorded C-MAPSS cycles, labelled simulated |
| 14 | MLOps: model registry, metrics, drift, promotion policy | partial — file+SQLite registry, PSI drift; MLflow deferred |
| 15 | FastAPI backend, versioned API, schemas, health checks | implemented |
| 16 | Frontend command centre | implemented |

`TASKS.md` is the authoritative status list; this table is a summary only.

## 6. Datasets

- **NASA C-MAPSS** (FD001 primary; FD002–FD004 available) — fleet telemetry,
  RUL, degradation, anomaly detection, health, maintenance.
- **UCI AI4I 2020** — supervised failure classification, failure modes,
  imbalanced learning, explainability.
- **NASA IMS Bearing** — planned; large, and requires a vibration-specific
  pipeline. Not integrated yet.

Datasets are never merged: they have different units, sampling and failure
definitions. Each has its own adapter and its own model family.

## 7. What "done" means

A clean clone can: install dependencies, fetch data, run one build command,
start the API, start the UI, and see every page populated by real model output —
with tests covering the data transformations, model training contracts and API
behaviour, and documentation that explains *why* each model is used.
