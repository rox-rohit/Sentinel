# Model Evaluation Report

All numbers below were produced by `python -m sentinel.pipelines.build` on
2026-11-14 and are reproducible with a fixed seed (42). They are reported from
held-out or official test splits, never from training folds.

## 1. RUL regression — NASA C-MAPSS FD001

**Protocol.** 80 units train / 20 units validation for selection (all cycles,
engine-wise). The selected model is refit on all 100 training units and scored
once on the 100 official test units at each unit's final recorded cycle.

### Model comparison (held-out engines)

| Model | MAE | RMSE | NASA score | Bias |
|---|---|---|---|---|
| **Ridge (selected)** | **10.65** | **13.61** | **9,448** | +0.21 |
| Random Forest | 10.84 | 15.13 | 16,656 | −0.62 |
| XGBoost | 10.63 | 14.77 | 16,674 | −0.67 |

### Official test set

| Metric | Value |
|---|---|
| MAE | 12.60 cycles |
| RMSE | 15.71 cycles |
| NASA score | 335.42 |
| Bias | −0.86 cycles |
| p90 absolute error | 25.30 cycles |
| Units | 100 |

### Interpretation

- The **linear baseline wins the asymmetric score by a wide margin**, despite
  XGBoost having a marginally better MAE (10.63 vs 10.65). The NASA function
  penalises late predictions far more than early ones, and the tree ensembles
  produce more late errors on this feature set. This is an honest negative
  result for the more complex models and is shown in the UI.
- Residual p10/p90 are −19.15 / +17.61 cycles, with p50 = 0.0 — the model is
  essentially unbiased at the median, so the 80% band is roughly symmetric.
- Early-life rows cannot be scored until the 30-cycle window fills, which is why
  17,731 of 20,631 training rows are usable. This is a real constraint of causal
  features and is documented rather than imputed away.

### Why clipping at 125

Run-to-failure trajectories give unbounded targets for healthy engines, but the
sensors cannot distinguish 150 from 300 cycles of remaining life. Unclipped
targets let long healthy trajectories dominate the loss. The clip is applied to
targets and predictions, surfaced in the API and the UI.

## 2. Failure classification — UCI AI4I 2020

**Protocol.** Stratified 75/25 split (7,500 / 2,500 rows, 85 positives in test).
5-fold stratified CV on the training split for model selection. Threshold tuned
on out-of-fold probabilities by expected cost (FN 500, FP 50).

| Model | CV PR-AUC | Test PR-AUC | Recall | Precision | F1 | Threshold |
|---|---|---|---|---|---|---|
| **Random Forest (selected)** | **0.889** | 0.864 | 0.847 | 0.818 | 0.832 | 0.28 |
| HistGradientBoosting | 0.886 | **0.899** | 0.835 | 0.845 | 0.840 | 0.24 |
| XGBoost | 0.862 | 0.861 | 0.859 | 0.670 | 0.753 | 0.45 |
| Extra Trees | 0.815 | 0.797 | 0.788 | 0.593 | 0.677 | 0.39 |
| Logistic Regression | 0.487 | 0.439 | 0.671 | 0.348 | 0.458 | 0.77 |

Selected model: **Random Forest**, threshold 0.28.

Confusion matrix (TN 2,399 · FP 16 · FN 13 · TP 72), FPR 0.66%, FNR 15.3%.
Expected cost on the test split: **7,300 cost units**.

**Calibration.** Brier 0.00945 versus a 0.03284 base-rate baseline; the
reliability table is in the Explainability page. No post-hoc calibrator is used.

### Interpretation

- HistGradientBoosting has the best test PR-AUC (0.899 vs 0.864) but slightly
  lower CV PR-AUC. Selection uses CV, because tuning on the test split is
  leakage; the gap is reported rather than hidden.
- Logistic Regression is dramatically worse (PR-AUC 0.439), confirming the
  relationships are non-linear (threshold physics in the label construction).
- Recall 84.7% means roughly 1 in 6 failures is missed at the cost-optimal
  threshold; the cost model can be changed to trade FPs for recall.

### Failure modes

| Mode | Training support | Test PR-AUC | Status |
|---|---|---|---|
| Tool wear failure | 33 | 0.067 | modelled — weak signal |
| Heat dissipation failure | 79 | 0.954 | modelled |
| Power failure | 78 | 1.000 | modelled |
| Overstrain failure | 78 | 1.000 | modelled |
| Random failure | 13 | — | insufficient support, not modelled |

PWF/HDF/OSF are deterministic functions of recorded channels in AI4I, so their
near-perfect scores measure label construction, not field prediction. TWF is
genuinely hard and reported as such. The five mode labels are not an exact
partition of the union label (27 failure rows with no mode; 42 mode rows with no
failure flag).

## 3. Anomaly detection

Fitted on 3,100 early-life rows (cycles 30–60) of training units; 13,096 test
cycles scored. Ensemble = mean of p99-normalised IsolationForest, LOF and PCA
reconstruction error. Severity thresholds are healthy-distribution percentiles
(p90 = 0.844, p97 = 0.900, p99.5 = 0.994, p99.9 = 1.074).

Distribution over the fleet's current cycle: 75 normal, 7 low, 10 medium,
1 high, 7 critical. The fleet mixes units early and late in life, so the band
distribution is informative rather than saturated.

## 4. Drift

PSI on ten C-MAPSS sensors (units ≤ median vs units > median) and five AI4I
features (first vs second half of the process sequence). Worst PSI 0.773 →
overall status `drift`. For C-MAPSS this is expected: unit-to-unit variation and
degradation dominate. It is reported as distribution change, not as a pipeline
fault.

## 5. Decision scenario (current build)

| Strategy | Cost | Downtime | Serviced |
|---|---|---|---|
| Reactive (run to failure) | $8,455 | 304 h | 0 |
| Preventive (service all 100) | $12,000 | 400 h | 100 |
| **Predictive (budget $2,500)** | **$3,274** | 111 h | 20 |

These are scenario estimates under the stated cost assumptions, not measured
savings. The predictive strategy is cheaper because it services only assets with
positive expected benefit; deferred assets carry expected unplanned losses.

## 6. Threats to validity

- C-MAPSS is simulated; FD001 has one operating condition. Results may not
  transfer to multi-condition fleets without normalisation.
- AI4I is synthetic and its labels are threshold-derived.
- The health score has no ground-truth target to validate against; it is a
  transparent decision aid.
- Costs are assumptions, so the optimiser's choices are conditional on them.

---

## Sensor forecasting (C-MAPSS FD001)

Chronological per-engine split, 14,394 training rows and 6,237 test rows across
100 engines. Mean MASE over horizons 1, 5 and 10 and four sensors:

| Model | Mean MASE | Outcome |
|---|---|---|
| Exponential smoothing (α = 0.3) | **0.881** | Selected; wins all 12 sensor × horizon cells |
| Moving average (15) | 0.987 | Beats persistence, loses to smoothing |
| Persistence | 1.061 | Reference baseline |
| HistGradientBoosting (change target) | 1.054 | Loses on the held-out tail |

MASE is averaged only because it is scale-free; MAE is reported per sensor and
horizon because the channels carry different units.

**Why smoothing wins.** These four C-MAPSS channels are smooth, slowly drifting
signals. Exponential smoothing carries the current level and adapts to the
degradation trend, while a tree model trained on early life must extrapolate a
level it has never seen. Forecasting the *change* instead of the level improved
the boosted model (MASE 1.08 → 1.01 at h=1 on `s3`) but did not close the gap.
This is recorded as a negative result rather than tuned away; a future
sequence model (LSTM/GRU) is the natural next comparison and remains blocked by
the environment (D-008).
