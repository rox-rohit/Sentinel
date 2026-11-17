# ML Methodology

This document records *why* each model and validation protocol is used, including
known weaknesses.

## 1. Leakage control

- **RUL:** split by engine (`GroupKFold` / 80-20 engine-wise). No engine appears
  in both train and validation. The official C-MAPSS test trajectories are scored
  once, after refitting on all training engines.
- **Features:** rolling statistics are causal and use `min_periods = window`;
  no centred windows, no global normalisation fitted on the test period. The
  feature builder rejects frames whose per-entity time order is not increasing.
- **Classification:** stratified split; the decision threshold is tuned on
  out-of-fold training probabilities, never on the test split.
- **Fleet state:** built from the held-out test trajectories, so displayed RUL is
  out-of-sample. Within the fleet table, each asset is scored by a model trained
  on the 100 training units only.

## 2. Feature engineering

For C-MAPSS, per engine and channel:

- rolling mean / std / min / max over windows 5, 15, 30 cycles;
- EMA spans 10 and 30;
- lags 1 and 5, first differences at the same lags;
- 21 sensors → 378 candidate features, constants dropped at selection time.

For AI4I (tabular), four deterministic transforms plus one-hot product type:
temperature delta, mechanical power (`torque × rpm × 2π/60`), tool-wear × torque
(overstrain proxy) and thermal gradient per rpm. No target-derived features.

Feature definitions and versions are stored as `FeatureSpec` records
(`fs-v1`), so a model card can state exactly what it consumed.

## 3. RUL regression

**Target.** RUL = last recorded cycle − current cycle for training trajectories;
official RUL at the final cycle for test trajectories. Targets are clipped at
125 cycles. Rationale: sensor signatures far from failure are indistinguishable
from healthy operation, so unbounded targets add label noise and let long
trajectories dominate the loss. The clip is visible in every prediction and
documented on the RUL page.

**Candidates.** Ridge (scaled), Random Forest, XGBoost (hist). Selection uses
the NASA asymmetric score, tie-broken by RMSE, because late predictions are the
expensive failure mode in maintenance planning.

**Metrics.** MAE, RMSE, bias, p90 absolute error and the NASA score
(early: `exp(-d/13) − 1`, late: `exp(d/10) − 1`, summed).

**Uncertainty.** The residual distribution on held-out engines supplies p10/p90
interval offsets and an empirical CDF. Horizon risk is
`P(RUL ≤ H) ≈ F_residual(H − RUL̂)`. This is a model-derived probability under
the exchangeability assumption, not a calibrated guarantee.

**Observed result.** Ridge wins the NASA score (9,448 vs ~16,660 for the tree
ensembles) despite marginally higher MAE than XGBoost. Tree models produce more
late predictions on this feature set; this is reported, not hidden.

## 4. Failure classification (AI4I)

**Protocol.** 75/25 stratified split, 5-fold stratified CV on the training
split, class-imbalance handling (`class_weight` / `scale_pos_weight`), then a
single test evaluation.

**Selection metric.** Cross-validated PR-AUC. Accuracy is meaningless at a 3.4%
positive rate; recall alone can be gamed by predicting everything positive.

**Threshold.** Chosen on out-of-fold probabilities by expected cost
`FN × 500 + FP × 50`, using the configurable cost model. The active threshold is
stored with the model and reused by the API.

**Calibration.** Reliability table (8 quantile bins) and Brier score versus the
base rate are reported. No post-hoc calibrator is applied, so the reported
probabilities are the model's own.

**Failure modes.** One-vs-rest Random Forest per labelled mode. Modes with fewer
than 30 training cases are not trained and are shown as `insufficient_support`.
PWF/HDF/OSF are threshold-defined in the dataset, so their near-perfect PR-AUC is
a property of label construction; TWF is genuinely hard.

## 5. Anomaly detection

Fitted only on early-life windows (cycles 30–60) of training units, where the
engine is still healthy:

- IsolationForest on the full 378-feature vector;
- LocalOutlierFactor (novelty) on a compact degradation subset;
- PCA reconstruction error on the same compact subset.

Each score is normalised by its healthy p99 and the three are averaged.
Severity bands are percentile cuts of the healthy ensemble distribution
(p90/p97/p99.5/p99.9). The score measures distance from healthy behaviour — not
failure probability — and the UI says so.

## 6. Explainability

- Global: permutation importance on the held-out split (PR-AUC drop).
- Local: occlusion attribution — each feature is replaced by the training median
  and the probability change is recorded. This works for any model and is
  labelled as local sensitivity, not additive SHAP.
- Exact TreeSHAP is implemented (`XGBoost pred_contribs`) and used when the
  active classifier is a tree booster.
- All explanations are generated from the fitted artifact and the actual input;
  none are templated per asset.

## 7. Health scoring (transparent, configurable)

`health = 0.45·RUL_headroom + 0.25·(1 − risk₃₀) + 0.20·anomaly_health + 0.10·trend_health`

Anomaly health is anchored to the calibrated baseline:
`100 × (1 − clip((score − healthy_median) / (high_threshold − healthy_median), 0, 1))`,
so a score the severity logic still calls normal does not read as machine damage.
Each component is 0–100 and returned with the total. Bands: healthy ≥ 80,
attention ≥ 60, warning ≥ 40, critical < 40. Weights and bands are exposed in
the API and the Settings page. This is a decision aid, not a physical index.

## 8. Maintenance optimisation

- Priority score combines risk, expected failure cost, criticality and RUL
  urgency.
- Selection is an exact 0/1 knapsack (dynamic programming, 25-cost-unit grid)
  maximising `Σ(risk × failure cost − planned cost)` under the budget.
- Scenarios: reactive (expected unplanned losses), preventive (service all) and
  predictive (planned + residual expected failures).
- Assumptions are returned with the plan and shown in the UI. Savings are
  scenario estimates, not measured plant outcomes.

## 9. Drift

Population Stability Index between reference and current samples, on AI4I sensor
features (first vs second half of the process sequence) and C-MAPSS sensors
(units ≤ median vs units > median). PSI ≥ 0.25 is flagged as drift. C-MAPSS PSI
includes genuine degradation, which is stated in the payload.

---

## Sensor forecasting

Task: from history up to cycle `t`, predict a sensor value at `t + h` for
horizons 1–10. This is not RUL and not a recursive simulation; each horizon has
its own direct model.

- **Causal features.** Lags 1/2/3/5/10, rolling mean and std over 5/15/30 cycles,
  one- and five-cycle differences, cycle index, current value and an
  exponentially smoothed level (α = 0.3). Every rolling window is shifted by one
  cycle, so a value at `t` cannot enter its own feature vector.
- **Models.** Persistence (last value repeated), 15-cycle moving average,
  exponential smoothing, and HistGradientBoosting on the same features.
- **Level handling.** Trees cannot output values outside their training range,
  and the held-out tail of a degrading engine sits above that range. The boosted
  model therefore predicts the **change** from the current value; the change is
  added back at prediction time.
- **Validation.** Chronological split inside every engine: first 70% of cycles
  train, remaining 30% test. No shuffling, no shared engine between train and
  test, no future windows.
- **Metrics.** MAE, RMSE and MASE. MASE divides the mean absolute error by the
  naive one-step error on training rows, so sensors with different units are
  comparable and a value below 1 means the model beats persistence.
