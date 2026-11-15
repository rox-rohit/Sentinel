# Dataset Documentation

Two integrations, deliberately separate. No feature vector mixes their channels.

## 1. NASA C-MAPSS — turbofan engine degradation

- **Source:** NASA Prognostics Center of Excellence; NASA Open Data Portal.
  Downloaded from the Zenodo mirror of `CMAPSSData.zip`.
- **Citation:** A. Saxena, K. Goebel, D. Simon, N. Eklund, “Damage Propagation
  Modeling for Aircraft Engine Run-to-Failure Simulation”, PHM 2008.
- **Licence:** NASA open data; retain attribution to NASA PCoE.
- **Files used:** `train_FD001.txt`, `test_FD001.txt`, `RUL_FD001.txt`
  (FD002–FD004 are supported by the adapter for generalisation checks).

### Structure

26 whitespace-separated columns, no header: unit, cycle, three operational
settings, 21 sensor channels. Training trajectories run to failure; test
trajectories stop before failure and the RUL file gives the true remaining life
at each unit's final cycle.

| Subset | Train units | Test units | Conditions | Fault modes |
|---|---|---|---|---|
| FD001 | 100 | 100 | 1 | 1 (HPC degradation) |
| FD002 | 260 | 259 | 6 | 1 |
| FD003 | 100 | 100 | 1 | 2 |
| FD004 | 248 | 249 | 6 | 2 |

### Validation findings

- 20,631 training rows, 100 units, no missing values.
- Six channels (`s1`, `s5`, `s10`, `s16`, `s18`, `s19`) are constant in FD001
  and are flagged, then dropped by the feature selector.
- Trajectory lengths vary from 128 to 362 cycles.
- Quality score 88/100: the deduction is outlier flags on genuine degradation
  excursions, which the pipeline reports but does not delete.

### Limitations

- Simulated engines, not factory assets. Sensor units are simulated physical
  quantities.
- RUL is measured in cycles, not calendar time.
- FD001 has a single operating condition; FD002/FD004 need condition
  normalisation before sensors are comparable.
- Trajectories end at failure, so targets beyond the clip horizon are not
  identifiable from the sensors.

## 2. UCI AI4I 2020 — milling-process failure classification

- **Source:** UCI Machine Learning Repository, dataset 601.
- **Citation:** S. Matzka, “Explainable Artificial Intelligence for Predictive
  Maintenance Applications”, PHM Asia Pacific 2020.
- **Licence:** CC BY 4.0.
- **Shape:** 10,000 rows, 14 columns, 3.39% positive (`Machine failure`).

### Structure

Air temperature, process temperature, rotational speed, torque, tool wear and a
product quality variant (L/M/H), plus five failure-mode indicators and their
union label.

### Validation findings

- No missing values; quality score 97.5/100.
- **Labels are not a strict partition.** 27 rows have `Machine failure = 1` with
  no mode flagged; 42 rows have a mode flagged with `Machine failure = 0`. The
  five mode columns total 373 positives against 339 union positives. This is a
  documented property of the published file and is why per-mode metrics are
  reported separately rather than derived from the union label.
- Failure modes are extremely imbalanced: TWF 46, HDF 115, PWF 95, OSF 98,
  RNF 19 occurrences. RNF is not modelled (fewer than 30 training cases).

### Limitations

- Synthetic milling simulation with no timestamps or machine continuity: rows are
  independent process steps, so this dataset cannot drive a fleet timeline.
- PWF, HDF and OSF are deterministic threshold functions of the recorded
  channels. Near-perfect per-mode PR-AUC therefore reflects label construction,
  not field predictive power. This is stated in the UI.
- Tool-wear failure is rare and weakly identifiable (PR-AUC ≈ 0.07), a genuine
  negative result.

## 3. NASA IMS Bearing — planned, not integrated

Vibration run-to-failure data, useful for signal-processing and bearing
degradation. Not integrated: it is large and requires a vibration-specific
feature path (FFT/envelope features) that does not exist yet. It is listed as
pending in `TASKS.md` rather than claimed as supported.

## Handling rules

1. Datasets are fetched by `scripts/fetch_data.py`, never committed.
2. Each dataset has its own adapter and canonical schema in
   `sentinel/data/adapters/`.
3. Validation runs before preprocessing; schema errors block the build.
4. Processed frames are written as parquet with a content-hash version and a
   quality report in the metadata store.
5. Attribution and licence notes are kept in this file and in adapter metadata.
