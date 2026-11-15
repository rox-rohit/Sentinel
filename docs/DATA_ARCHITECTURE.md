# Data Architecture

## Flow

```
data/raw/<dataset>/          source files, git-ignored, fetched by scripts/fetch_data.py
        │  adapter.load_raw()
        ▼
adapter.canonicalize()        canonical column names, dtypes, RUL derivation
        │
        ▼
validate_dataset()            schema / dtype / duplicate / outlier / time checks
        │  blocking on schema errors
        ▼
clean_frame()                 duplicate removal, optional median imputation (off by default)
        │
        ├── data/processed/*.parquet      analytical copy
        └── store.datasets                version (content hash), rows, quality JSON, schema JSON
```

## Canonical schemas

### C-MAPSS

`asset_id`, `cycle`, `op1..op3`, `s1..s21`, `split`, `rul`.

- `rul` is derived for training trajectories (last cycle − cycle).
- Test trajectories receive the official RUL only at their final cycle; other
  rows stay null (unknown truth, not zero).
- Rows are sorted by `(asset_id, cycle)` after cleaning.

### AI4I

`row_id`, `asset_id`, `product_type`, `air_temp_k`, `process_temp_k`,
`rotational_speed_rpm`, `torque_nm`, `tool_wear_min`, `machine_failure`,
`failure_twf`, `failure_hdf`, `failure_pwf`, `failure_osf`, `failure_rnf`.

No time axis. This frame is used only for tabular supervised learning.

## Validation rules

| Rule | Severity |
|---|---|
| Required canonical columns present | error |
| Numeric/datetime dtype correctness | error |
| Missing values < 20% | warning |
| Missing values ≥ 20% | error |
| Fully duplicated rows | warning |
| Duplicated `(id, time)` keys | error |
| Non-monotonic time inside an entity | error |
| Non-contiguous cycles | warning |
| Constant channel | info |
| IQR outliers | info (flagged, never removed) |
| Negative value in a non-negative channel | warning |
| Classification target has one class | error |
| Failure rate / target range | info |

Quality score = 100 − (15·errors + 3·warnings + 0.5·info), floored at 0.
The UI shows the score and the individual findings.

## Versioning

Dataset versions are the first 12 hex characters of a SHA-256 over the canonical
frame's row hashes. Re-running the build on unchanged data does not create a new
version. The raw/processed split is preserved: raw is never mutated.

## Storage choices

| Data | Store | Reason |
|---|---|---|
| Analytical frames | Parquet (`data/processed`) | columnar, typed, fast reload |
| Dataset versions, model registry, alerts | SQLAlchemy (`artifacts/sentinel.db`) | relational metadata, PostgreSQL-ready |
| Models | joblib (`artifacts/models`) | versioned artifacts with metadata envelope |
| Metrics and cards | JSON (`artifacts/meta`) | reproducible, diffable |
| UI payload | `artifacts/snapshot.json` + `src/generated/snapshot.json` | one build artifact for offline UI |

`SENTINEL_DATABASE_URL` switches the metadata store to PostgreSQL without code
changes. Raw files, models and snapshots are git-ignored.

## Why the snapshot exists

The hosted frontend cannot execute Python. The snapshot is a *derived artifact*
containing fleet state, model metrics, EDA, registry and decisions for the last
build, so the UI can demonstrate real outputs without a server. It is labelled
as "Artifact snapshot" in the UI and is never described as live data.

## Future extension points

- `register_adapter(name, factory)` for new datasets.
- `ModelAdapter` contract for new model families.
- Condition normalisation for FD002/FD004 (six operating conditions).
- Streaming ingestion (MQTT/ESP32) would write into the same canonical frame and
  reuse the existing feature and inference path.
