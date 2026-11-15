# Experiment Log

Chronological record of verified runs. Each entry states the hypothesis, the
protocol and the outcome — including failures and rejected ideas.

## 2026-11-14 — Environment inspection

- Python 3.15.0, Node 24.21.0, RTX 3050 Laptop (4 GB), ~3.5 GB free disk.
- Installed and verified: numpy 2.5.4, pandas 3.1.0, scipy 1.18.1,
  scikit-learn 1.9.1, xgboost 3.4.1, pyarrow, fastapi, sqlalchemy, pytest.
- **Rejected:** CUDA PyTorch / `shap` / MLflow / LightGBM / CatBoost installs —
  disk budget and Python 3.15 wheel availability. Baselines were prioritised;
  the feature path stays tensor-ready.

## 2026-11-14 — Data ingestion and validation

Hypothesis: both datasets map cleanly to the canonical schemas.

- C-MAPSS: 20,631 rows, 100 units, no missing; six constant channels; quality
  88/100 due to genuine outlier excursions.
- AI4I: 10,000 rows, 3.39% failures; quality 97.5/100.
- **Finding:** AI4I mode labels are not a strict partition of `Machine failure`
  (27 failure rows with no mode, 42 mode rows with no failure). Documented and
  asserted in `tests/test_data_pipeline.py`.

## 2026-11-14 — Feature pipeline

Hypothesis: causal rolling features are leakage-free and group-isolated.

- 378 features from 21 sensors (windows 5/15/30; EMA 10/30; lags/deltas 1/5).
- Causality test: mutating future cycles does not change past features. Group
  test: engine 2 never sees engine 1's history.
- **Bug found and fixed:** `windows=()` fell back to defaults, so an explicit
  empty request silently produced features. Defaults are now applied only for
  `None`.

## 2026-11-14 — RUL model selection

Hypothesis: gradient boosting beats a linear baseline on sensor windows.

- Result: **rejected.** Ridge achieved the best NASA score (9,448) against
  Random Forest (16,656) and XGBoost (16,674), with MAE 10.65 vs 10.63/10.84.
- Official test: MAE 12.60, RMSE 15.71, NASA 335.4.
- Interpretation: with causal, heavily correlated rolling features, the linear
  model is stable and produces fewer late predictions; tree ensembles add
  variance without improving the asymmetric tail. Ridge remains the active model.

## 2026-11-14 — Failure classifier comparison

Hypothesis: non-linear ensembles substantially beat logistic regression.

- Confirmed: RF CV PR-AUC 0.889 vs LR 0.487; test PR-AUC 0.864 vs 0.439.
- HistGradientBoosting had the best test PR-AUC (0.899) but a lower CV score
  (0.886); selection stayed with CV to avoid test leakage.
- Cost-optimal threshold 0.28: recall 0.847, precision 0.818, 13 missed failures
  and 16 false alarms out of 2,500 records.
- Failure modes: PWF/HDF/OSF near 1.0 PR-AUC because AI4I defines them by
  thresholds on the same channels; TWF PR-AUC 0.067 (weak, reported as such).

## 2026-11-14 — Fleet assembly correction

Hypothesis: using the last cycle of each training trajectory is a valid fleet
view.

- **Rejected.** Every training unit ends at failure, so all 100 assets appeared
  critical with mean RUL 1.5 cycles — useless for operations.
- Fix: fleet state now comes from the 100 held-out test trajectories, which stop
  before failure and carry official RUL labels. Result: 14 healthy, 52 attention,
  16 warning, 18 critical; mean RUL 74.7 cycles. Predictions are out-of-sample.

## 2026-11-14 — Anomaly calibration

- Fitted on 3,100 healthy rows (cycles 30–60); scored 13,096 test cycles.
- Healthy p90/p97/p99.5/p99.9 thresholds produced a usable spread of severities
  (75 normal, 7 low, 10 medium, 1 high, 7 critical at the fleet's current cycle),
  confirming the detector separates early-life from near-failure behaviour.
- **Correction:** the first health formula mapped raw anomaly score to health,
  making normal readings look damaged. It is now anchored between the healthy
  median and the high-severity threshold, and the asset page exposes all four
  components.
- Limitation: FD001 is single-condition; calibration does not transfer to FD002
  without condition normalisation.

## Next experiments (planned)

1. Condition normalisation for FD002/FD004 and a cross-subset generalisation test.
2. Sequence models (LSTM/GRU/1D-CNN) once PyTorch is installed, compared against
   the Ridge baseline on the same engine-wise split.
3. Sensor forecasting baselines with chronological validation.
4. Drift-triggered retraining with a documented promotion policy.
