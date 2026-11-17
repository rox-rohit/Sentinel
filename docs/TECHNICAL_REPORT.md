# SENTINEL — Technical Report

**Industrial Intelligence & Predictive Maintenance Platform**
Version 0.4.0 · build `sentinel-phase3` · 17 November 2026

---

## Abstract

SENTINEL is an end-to-end predictive-maintenance platform built on two public
research datasets: NASA C-MAPSS turbofan degradation trajectories and the UCI
AI4I 2020 milling-process dataset. It ingests and validates raw data, engineers
causal time-series features, trains and compares several model families, turns
predictions into health scores and budget-constrained maintenance plans, and
exposes all of it through a FastAPI service and a React operations console.

The work deliberately favours evidence over capability. Every displayed number
is produced by a reproducible pipeline; metrics are reported from held-out
engines or official test splits; and three results contradict the expected
"more complex is better" narrative:

1. A **linear Ridge model beats both tree ensembles** on the asymmetric NASA RUL
   score (9,448 vs ~16,600) despite XGBoost having a marginally lower MAE.
2. **Exponential smoothing beats gradient boosting** for sensor forecasting
   (mean MASE 0.881 vs 1.054) across all twelve sensor × horizon cells.
3. **HistGradientBoosting has the best test PR-AUC** for failure classification
   (0.899 vs 0.864 for the selected Random Forest), but the selection used
   cross-validation because tuning on the test split is leakage. The gap is
   reported rather than hidden.

The engineering claims are backed by 49 backend tests, a three-test Worker
suite, a clean TypeScript build, a CI pipeline that rebuilds every artifact on
each push, and browser checks against the running console.

---

## 1. Problem and scope

Industrial maintenance teams face a sequencing problem, not just a prediction
problem: knowing that an asset will fail is useful only if the response fits a
budget, a downtime window and a criticality ranking. SENTINEL therefore spans
four questions:

| Question | Module | Output |
|---|---|---|
| Is this behaviour abnormal? | Anomaly ensemble | Score, severity, attributed sensors |
| Will it fail, and how soon? | Classifier + RUL regression | Failure probability, remaining cycles, risk bands |
| Why does the model think so? | Explainability | Attributions, calibration, failure modes |
| What should we do? | Decision layer | Health score, prioritised plan, scenario costs |

**Out of scope by design:** live PLC/SCADA ingestion, physics simulation, and
guaranteed failure dates. The platform is an analytical digital twin over
recorded telemetry, labelled as such in the interface.

### 1.1 Datasets

| Dataset | Rows | Units | Use |
|---|---|---|---|
| NASA C-MAPSS FD001 | 20,631 | 100 | RUL regression, anomaly detection, replay, forecasting |
| UCI AI4I 2020 | 10,000 | — | Failure classification, failure modes, explainability |

C-MAPSS is simulated run-to-failure data with one operating condition. AI4I is
synthetic, with failure labels derived from physical thresholds. Both facts
bound what the results can claim; see §7.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ React 19 + TypeScript + Tailwind 4 + Recharts (Vite SPA)         │
│ 13 pages · design system · live API mode / snapshot fallback     │
└───────────────┬──────────────────────────────────────────────────┘
                │ HTTP /api/v1 (JSON), WebSocket /ws/replay/{asset}
┌───────────────▼──────────────────────────────────────────────────┐
│ FastAPI: routers → schemas → dependencies                        │
│  health · fleet · predictions · decisions · catalog · replay ·   │
│  alerts                                                          │
└───────────────┬──────────────────────────────────────────────────┘
                │ no HTTP concepts below this line
┌───────────────▼──────────────────────────────────────────────────┐
│ Inference services (snapshot cache, model loading, risk maths)   │
│ Decision layer (health scoring, knapsack planner, comparisons)   │
│ Model layer (RUL, classification, anomaly, forecast, registry)   │
│ Feature layer (causal rolling / lag / EMA, 378 specifications)   │
│ Data layer (adapters, validation, canonical schema, parquet)     │
└───────────────┬──────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────┐
│ SQLAlchemy store: datasets · models · alerts · maintenance       │
│ scenarios (SQLite locally, PostgreSQL via SENTINEL_DATABASE_URL) │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 Key architectural decisions

| Decision | Choice | Alternative rejected | Why |
|---|---|---|---|
| D-001 | Vite SPA + separate API | Next.js full-stack | The ML stack is Python; the console is a client, not a server |
| D-004 | Live API, committed artifact snapshot fallback | Static-only demo | The console stays usable without Python while never inventing values |
| D-008 | Classical ML only | LSTM/Transformer lab | ~3.5 GB disk, no CUDA PyTorch, Python 3.15 wheels |
| D-011 | Replay recorded C-MAPSS cycles | Generated/simulated stream | Fabricating telemetry would undermine every displayed number |
| D-012 | Direct multi-horizon forecasting, per-engine chronological split | Recursive one-step model, random split | Recursion compounds error; shuffling leaks future cycles |
| D-013 | Alert lifecycle keyed by stable fingerprint | Rebuild deletes and reinserts | Acknowledgements must survive rebuilds |
| D-014 | Saved scenarios store the computed plan | Store budget and recompute | Recomputation would silently rewrite comparison history |

### 2.2 Contracts and failure behaviour

- **Snapshot contract.** `python -m sentinel.pipelines.build` writes
  `artifacts/snapshot.json`, `artifacts/replay.parquet`, model artifacts and
  registry rows. The UI consumes the snapshot directly when the API is absent
  and labels the mode in the top bar; it never fills missing fields with
  plausible-looking values.
- **Model registry.** Every build records algorithm, metrics, parameters and
  artifact path. The registry is append-only (see §8.3).
- **Operational store.** Alerts and saved maintenance scenarios live in the
  database rather than the snapshot, because they are user state that a rebuild
  must not overwrite.
- **Error handling.** Domain errors return a stable envelope
  `{error: {code, message}}`; missing artifacts return 503 rather than a
  partial payload.
- **CI.** GitHub Actions rebuilds datasets and models on every push, then runs
  `pytest`, `bun test`, `tsc --noEmit` and the production build. A green badge
  therefore means the pipeline still reproduces, not merely that unit tests
  pass.

---

## 3. Data and feature engineering

1. **Adapters** normalise both datasets into a canonical schema; C-MAPSS keeps
   unit/cycle identity, AI4I keeps process settings and failure-mode labels.
2. **Validation** reports schema, type, duplicate, outlier and constant-channel
   issues with a 0–100 quality score (C-MAPSS 88.0, AI4I 97.5).
3. **Features** include rolling mean/std/min/max, exponential moving averages,
   deltas and lags, all shifted so cycle `t` cannot contribute to its own
   feature vector. 378 feature specifications are versioned with the build.
4. **Leakage guards:** chronological ordering is preserved, rolling windows are
   right-aligned and shifted, and splits are grouped by engine (RUL) or
   stratified by label (classification).

The first 30 cycles of each engine cannot produce a complete feature vector, so
17,731 of 20,631 C-MAPSS rows are trainable. That is a real consequence of causal
features and is reported, not imputed away.

---

## 4. Modelling decisions and results

All numbers come from the build in this repository and are reproducible with
seed 42. Full tables: `docs/MODEL_EVALUATION.md`.

### 4.1 Remaining useful life (C-MAPSS FD001)

**Protocol.** 80/20 engine-wise split for selection; the winner is refit on all
100 training units and scored once on the 100 official test units at each unit's
final cycle. Targets and predictions are clipped at 125 cycles because sensors
cannot distinguish 150 from 300 cycles of remaining life.

| Model | Validation MAE | Validation RMSE | Validation NASA | Bias |
|---|---|---|---|---|
| **Ridge (selected)** | **10.65** | **13.61** | **9,448** | +0.21 |
| Random Forest | 10.84 | 15.13 | 16,656 | −0.62 |
| XGBoost | 10.63 | 14.77 | 16,674 | −0.67 |

**Official test (100 units): MAE 12.60 · RMSE 15.71 · NASA 335.4 · bias −0.86 ·
p90 absolute error 25.3.**

**Decision.** Select Ridge. XGBoost's MAE is 0.02 cycles better, but the NASA
score penalises late predictions exponentially, and the tree ensembles produce
more late errors. A 76% lower penalty is worth 0.02 cycles of MAE.

**Residual band.** p10 −19.15 / p90 +17.61 cycles, essentially symmetric. The
API returns this empirical band; it is not a calibrated prediction interval.

### 4.2 Failure classification (AI4I 2020)

**Protocol.** Stratified 75/25 split (7,500 / 2,500 rows, 85 positives in test);
5-fold stratified CV on train for selection; threshold tuned on out-of-fold
probabilities by expected cost (false negative 500, false positive 50).

| Model | CV PR-AUC | Test PR-AUC | Recall | Precision | F1 | Threshold |
|---|---|---|---|---|---|---|
| **Random Forest (selected)** | **0.889** | 0.864 | 0.847 | 0.818 | 0.832 | 0.28 |
| HistGradientBoosting | 0.886 | **0.899** | 0.835 | 0.845 | 0.840 | 0.24 |
| XGBoost | 0.862 | 0.861 | 0.859 | 0.670 | 0.753 | 0.45 |
| Extra Trees | 0.815 | 0.797 | 0.788 | 0.593 | 0.677 | 0.39 |
| Logistic Regression | 0.487 | 0.439 | 0.671 | 0.348 | 0.458 | 0.77 |

Test confusion matrix: TN 2,399 · FP 16 · FN 13 · TP 72 → FPR 0.66%, FNR 15.3%,
expected cost **7,300 units**. Calibration Brier **0.00945** against a 0.03284
base-rate baseline, with no post-hoc calibrator.

**Decision.** Select Random Forest on CV PR-AUC, not on the best test number.
The 0.035 test-PR-AUC advantage of HistGradientBoosting is reported on the Model
Laboratory page as an honest gap; choosing it after seeing test results would be
selection leakage.

### 4.3 Failure modes

| Mode | Train support | Test PR-AUC | Status |
|---|---|---|---|
| Tool wear (TWF) | 33 | 0.067 | modelled — weak signal |
| Heat dissipation (HDF) | 79 | 0.954 | modelled |
| Power (PWF) | 78 | 1.000 | modelled |
| Overstrain (OSF) | 78 | 1.000 | modelled |
| Random (RNF) | 13 | — | insufficient support, not modelled |

PWF, HDF and OSF are deterministic functions of recorded channels in AI4I, so
their near-perfect scores measure label construction, not field prediction. TWF
is the only genuinely difficult mode and performs poorly. Reporting 1.000 as a
capability without that caveat would be dishonest.

### 4.4 Anomaly detection

IsolationForest (full feature set), LOF (compact degradation subset) and PCA
reconstruction error are each normalised to their healthy p99 and averaged. The
ensemble is fitted on 3,100 early-life rows; 10,196 rows are scored. Severity
cuts come from the healthy score distribution: p90 0.844, p97 0.900, p99.5
0.994, p99.9 1.074. Current fleet distribution: 75 normal, 7 low, 10 medium,
1 high, 7 critical.

Severity is relative to an early-life baseline, so a brand-new asset is by
construction "normal" and a heavily degraded one is "critical". It is a
monitoring aid, not a failure probability.

### 4.5 Sensor forecasting

**Protocol.** Four C-MAPSS channels, horizons 1–10, direct models. Chronological
split inside every engine: first 70% of cycles train, remaining 30% test
(14,394 / 6,237 rows). MASE is scaled by the naive one-step error on training
rows, so below 1 means better than persistence.

| Model | Mean MASE (h = 1, 5, 10) | Outcome |
|---|---|---|
| **Exponential smoothing (α = 0.3)** | **0.881** | Selected; wins 12/12 cells |
| Moving average (15) | 0.987 | Beats persistence |
| Persistence | 1.061 | Reference |
| HistGradientBoosting (change target) | 1.054 | Loses on the held-out tail |

Exponential smoothing is 17.0% better than persistence. This is a negative
result for the boosted model and is documented as such.

### 4.6 Health score and maintenance plan

The health score is a weighted sum of four 0–100 components (RUL 0.45, horizon
risk 0.25, anomaly 0.20, trend 0.10) with bands healthy ≥ 80, attention ≥ 60,
warning ≥ 40, critical < 40. Weights are engineering judgement and published in
the API and Settings page; there is no ground-truth health target to validate
against.

The planner ranks candidates by risk, expected failure cost, criticality and RUL
urgency, then solves an exact 0/1 knapsack in 25-cost-unit steps under the
budget. Current build, budget **$2,500**:

| Strategy | Total cost | Downtime | Assets serviced |
|---|---|---|---|
| Reactive (run to failure) | $8,455 | 304 h | 0 |
| Preventive (service all) | $12,000 | 400 h | 100 |
| **Predictive (budget-constrained)** | **$3,274** | 111 h | 20 |

Planned spend is $2,400 with $5,181 expected avoided loss over the 20 selected
assets. These are scenario estimates under stated cost assumptions, not measured
plant savings.

Saved scenarios persist the full plan and compare 2–6 runs on avoided loss,
predictive cost, spend, downtime, serviced assets and avoided loss per $1,000
spent. In a live check, $600 bought 4 assets at $3,132 avoided loss per $1,000
spent, while $1,800 bought 14 assets at $2,680 per $1,000 — more total benefit,
less efficient per dollar. The comparison exposes that trade-off instead of
declaring a single winner.

---

## 5. Honest negative results

These are the results a portfolio project is usually tempted to omit.

1. **Tree ensembles lose to linear regression on the RUL objective.** XGBoost
   wins MAE by 0.02 cycles but loses the asymmetric NASA score by 76%. The
   selected model is the simpler one.
2. **Gradient boosting loses to exponential smoothing on sensor forecasting.**
   Even after diagnosing two real flaws — the smoothing feature was accidentally
   excluded, and trees were predicting absolute levels they cannot extrapolate —
   the boosted model's MASE only improved from 1.08 to 1.01 and still lost to
   smoothing (0.881). The flaw fixes are recorded; the loss is not tuned away.
3. **The best classifier on the test split is not the selected classifier.**
   HistGradientBoosting reaches 0.899 test PR-AUC versus 0.864 for Random
   Forest, but selection is CV-based. The gap is visible.
4. **Tool-wear failure detection is weak.** PR-AUC 0.067 on 13 test positives;
   the label is rare and not a deterministic function of the channels. The other
   near-perfect modes are near-perfect because of how AI4I constructs labels.
5. **Drift is flagged (`drift`, worst PSI 0.773) and is expected.** C-MAPSS
   units differ by degradation stage; PSI detects distribution change, not a
   broken pipeline. Presenting a green drift dashboard here would be misleading.
6. **Deep learning is absent.** It is deferred (D-008), not silently claimed.
   Sequence models remain the natural next comparison for forecasting and RUL.

---

## 6. Evaluation evidence

| Gate | Result |
|---|---|
| Backend tests | 49 passed (`pytest`) — data, validation, features, metrics, calibration, decisions, API, replay, WebSocket JSON safety, forecasting, alert lifecycle, scenario comparison |
| Worker tests | 3 passed (`bun test`) |
| Typecheck | clean (`tsc --noEmit`) |
| Production build | Vite + Worker build succeeds, `dist/sentinel/index.js` produced |
| CI | GitHub Actions rebuilds datasets, models and snapshot, then runs all gates on every push |
| Live checks | Alert acknowledgement persisted across a re-sync; maintenance scenarios saved, compared and deleted through the UI; replay streamed over WebSocket |

**What is not tested.** There are no React component tests, Playwright
end-to-end flows or accessibility audits. UI verification is manual browser
inspection against the live API. That is a real gap, listed in §8.

---

## 7. Limitations and threats to validity

### 7.1 Data
- C-MAPSS FD001 is simulated, single-condition, and only 100 units. Results may
  not transfer to multi-condition fleets without per-condition normalisation.
- AI4I is synthetic and its labels are threshold-derived; near-perfect failure
  modes are artefacts of that construction.
- No IMS Bearing or field data is integrated, so nothing here has been validated
  against measured maintenance outcomes.

### 7.2 Modelling
- RUL intervals are empirical residual quantiles, not calibrated conformal
  intervals; coverage is not guaranteed.
- The health score has no ground truth and its weights are judgement.
- Costs (failure cost, inspection cost, downtime) are assumptions; the
  optimiser's recommendations are conditional on them.
- Forecasting is univariate per sensor and covers four channels; cross-sensor
  structure is unused.
- Anomaly thresholds are calibrated on early-life healthy rows from the same
  fleet, which is optimistic for a genuinely new asset population.

### 7.3 Product and operations
- No authentication or role model. The alert inbox records `console-operator` as
  the actor; mutating endpoints accept a configured API key but there are no
  user identities.
- SQLite is the default store; PostgreSQL is supported by configuration but not
  exercised in CI.
- The console is not deployed publicly; screenshots come from a local run
  against the live API.
- The snapshot is loaded whole (653 KB); pagination and caching are not needed
  at 100 assets but would be at 10,000.
- No MQTT/OPC-UA ingestion, notification delivery, observability stack or
  backup strategy exists.
- The model registry is append-only: repeated builds insert duplicate rows for
  the same model instead of versioning a single logical entry, and promotion is
  metadata-only with no enforcement.
- Saved maintenance scenarios are immutable records of past runs. They
  intentionally do not track later fleet changes, so a saved plan can be stale
  relative to the current recommendation.

---

## 8. Reproducibility and engineering practices

```bash
python scripts/fetch_data.py              # datasets are not redistributed
python -m sentinel.pipelines.build        # ~3 min; artifacts, registry, snapshot
python -m pytest -q                       # 49 tests
python -m uvicorn sentinel.api.main:app --port 8000
bun install && bun run dev                # console on :5173
```

- Fixed seeds throughout; the build is deterministic apart from timestamps.
- Metrics are written by the pipeline, not typed into the UI.
- Every page reads only fields present in the snapshot or API contract, and the
  top bar labels live versus artifact-snapshot mode.
- Decisions with alternatives are recorded in `DECISIONS.md` (D-001 … D-014).
- Commits are authored solely by the repository owner, with no AI attribution.

---

## 9. Future work

In value order:

1. **Deploy a working demo** (hosted UI + Python API + PostgreSQL). Everything
   else becomes verifiable by a reviewer in seconds.
2. **Real ingestion path** — canonical column mapping, asset registry, an
   OPC-UA or MQTT connector prototype.
3. **Policy backtesting** — measure whether predictive maintenance beats
   preventive and reactive policies on held-out trajectories, with cost-model
   sensitivity, instead of only scenario arithmetic.
4. **Conformal RUL intervals** with measured coverage, replacing residual
   quantiles.
5. **Closed-loop retraining** — drift triggers a candidate, evaluation gates
   promotion, regression refuses it.
6. **Identity, roles and scoped API keys**; Postgres migrations and backups.
7. **Frontend and end-to-end tests**, plus an accessibility pass.
8. **Multi-condition generalisation** on FD002–FD004 and model cards.

Deep learning stays deferred until the environment supports it and there is
evidence it beats the current baselines.

---

## Appendix — API surface

| Area | Endpoints |
|---|---|
| System | `GET /health`, `GET /system/status`, `POST /system/reload` |
| Fleet | `GET /fleet/summary`, `GET /fleet/assets`, `GET /fleet/assets/{id}` |
| Prediction | `POST /predict/failure`, `POST /predict/failure/explain`, `POST /predict/rul`, `GET /predictions`, `GET /rul`, `GET /anomalies`, `GET /explainability`, `GET /forecast` |
| Decisions | `GET /maintenance`, `POST /maintenance/optimize`, scenario CRUD + `GET /maintenance/scenarios/compare` |
| Alerts | `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve` |
| Catalog | `GET /datasets`, `GET /datasets/{name}/quality`, `GET /models`, `GET /eda`, `GET /drift` |
| Replay | `GET /replay/units`, `WS /ws/replay/{asset_id}` |

Full request/response detail: `docs/API_DOCUMENTATION.md`. OpenAPI is served at
`/docs` when the API runs.
