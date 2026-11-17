# SENTINEL — Demo Narrative & Three-Minute Walkthrough

## The story in one paragraph

A maintenance team does not need another dashboard; it needs to know which of a
hundred engines to touch this month, why the model says so, and what the
alternative costs. SENTINEL follows one thread from raw telemetry to a signed-off
decision: validated data, a health score per asset, a failure probability and a
remaining-life estimate, an explanation of the drivers, a budget-constrained
plan with its trade-offs, and an alert inbox where an operator acknowledges and
resolves what the models surface. Every number on screen comes from a training
run you can reproduce, and the places where the simple model won are shown, not
hidden.

## The three-minute script

**Before you start**

- API on `:8000`, console on `:5173`, browser zoom 100%, window 1440 × 900.
- Start on **Fleet Overview**. Do not scroll before the first sentence.
- Have the **RUL Intelligence** and **Forecasting** pages pre-warmed in tabs if
  the machine is slow.
- Fallback: if the API is down, the console switches to snapshot mode and the
  top bar says so. Say that line out loud instead of apologising.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:20 | Fleet Overview | "This is a fleet of 100 turbofan engines from NASA's C-MAPSS run-to-failure dataset. Every value here was produced by a build you can run: 57 healthy, 17 predicted to fail within 30 cycles, average health 72.5 out of 100." |
| 0:20–0:40 | Point to the health matrix / risk distribution | "Health is a published weighted score — RUL, 30-cycle risk, anomaly score and degradation trend. It is decision support, not a physical law, and the weights are on the Settings page." |
| 0:40–1:00 | Open an asset, e.g. **Unit 024** | "Drill into an engine and you get its recorded trajectory and the model's view at the last cycle: remaining life, the empirical band, and the sensors driving the anomaly." |
| 1:00–1:25 | **RUL Intelligence** | "RUL is scored on the official 100-unit test set, engines never seen in training: MAE 12.6 cycles. Ridge wins here — XGBoost's MAE is 0.02 cycles better, but the NASA score punishes late predictions, and the trees are 76% worse on that. We kept the simpler model." |
| 1:25–1:45 | **Forecasting** | "For sensor forecasting we compared persistence, smoothing and gradient boosting with a chronological split inside every engine. Exponential smoothing wins all twelve sensor-horizon cells; the boosted model loses. That negative result is in the report." |
| 1:45–2:10 | **Maintenance Optimiser** | "Now the decision. Under a $2,500 budget the planner services 20 assets for $2,400. Run-to-failure costs about $8,455 in expectation, service-everything $12,000, the predictive plan $3,274. These are scenario estimates under stated cost assumptions — not measured savings." |
| 2:10–2:30 | Saved scenarios panel | "Save this plan, re-optimise at a different budget, and compare. Here $600 buys four assets with higher avoided loss per dollar; $1,800 buys fourteen with more total benefit. The tool shows the trade-off instead of pretending one budget is best." |
| 2:30–2:50 | **Anomaly Centre** → alert inbox | "Alerts are the operational loop. I can acknowledge and resolve here. State is stored with actor and timestamp in the database, and it survives a full model rebuild — the fingerprint keeps the alert identity stable." |
| 2:50–3:00 | Back to Fleet Overview | "Underneath: causal features, engine-wise splits, 49 backend tests, and CI that retrains everything on every push. The limitations are in the README; the negative results are in the report." |

**Closing line (use verbatim):**
"The interesting part isn't that it predicts. It's that it shows where prediction
is unreliable, what a decision costs, and which model lost — so the numbers can
be trusted enough to act on."

## If you have eight minutes instead

1. **Fleet → asset** (2 min): telemetry, health components, anomaly attribution.
2. **Explainability** (1.5 min): permutation importance plus one local
   attribution, and the caveat that attribution is model behaviour, not physics.
3. **Model Laboratory** (1 min): registry, model comparison, drift — and the
   honest note that C-MAPSS drift is expected degradation.
4. **Maintenance → saved scenarios** (1.5 min): save two budgets, compare,
   highlight efficiency versus total benefit.
5. **Live Monitoring** (1.5 min): replay a recorded trajectory over WebSocket,
   state the "simulated replay, not a live feed" label.
6. **Close** (0.5 min): architecture and CI.

## Demo narrative: the longer telling

Most predictive-maintenance demos stop at a confusion matrix. The hard part in
practice is the hand-off: a prediction becomes useful only when it is attached to
an asset, a cost, a window and a person who owns the response. SENTINEL is built
around that hand-off.

The fleet view establishes scale and condition. The asset view answers "why this
one". The model pages establish whether the answers are trustworthy, including
the uncomfortable comparisons. The maintenance optimiser converts risk into a
plan under a budget and shows what the alternatives would cost. The alert inbox
closes the loop: something was noticed, someone acknowledged it, someone resolved
it, and the record survives the next retrain. The saved scenarios complete the
audit trail — a decision made last week can still be reconstructed and defended.

The thread is deliberately narrow: 100 engines, two public datasets, one cost
model. That is enough to demonstrate the architecture and the evaluation
discipline without pretending to be a deployed plant system.

## Questions to expect

**"Is this real data?"**
No. C-MAPSS is simulated run-to-failure data; AI4I is synthetic with
threshold-derived labels. The value is the pipeline and the evaluation method,
not the specific accuracy. That is stated on the pages and in the README.

**"Why not deep learning?"**
The environment has no CUDA PyTorch and about 3.5 GB free; it is deferred rather
than claimed. The baselines are strong enough that an LSTM would need to beat
Ridge's NASA score and smoothing's MASE to justify itself.

**"How do you know the model isn't leaking?"**
Engine-wise splits for RUL, chronological per-engine splits for forecasting,
stratified splits for classification, and all rolling features shifted so cycle
`t` never enters its own feature vector. There are tests for the shift.

**"What would you do first in production?"**
Connect a real source, then backtest the maintenance policy against historical
work orders. Prediction accuracy is not the bottleneck; decision quality is.

**"What's the weakest part?"**
Two things: there is no authentication, so the actor on an alert is a
placeholder, and there are no frontend end-to-end tests. Both are listed as
limitations rather than glossed over.
