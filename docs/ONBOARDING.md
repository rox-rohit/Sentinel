# Real-Plant Onboarding

How a customer CSV becomes a registered SENTINEL asset — and why nothing is
scored until validation passes.

## The problem

The research adapters know their files: C-MAPSS is whitespace-separated with
fixed column names, AI4I has a published header. A plant historian export has
neither. Column names are local (`Engine ID`, `T24`, `Comp_A_Speed`), sensors are
partial, cycles may be duplicated, and units are undocumented.

Onboarding makes that mapping explicit and auditable instead of guessing.

```
customer CSV
    │  POST /onboarding/inspect        parse, infer, suggest mapping
    ▼
column mapping (source → canonical)
    │  POST /onboarding/validate       coerce + structural checks + scoring gate
    ▼
validation report (blocked / warnings / ready)
    │  POST /onboarding/import         refused if blocked
    ▼
one parquet per asset + registry row (exact mapping stored)
    │  POST /onboarding/assets/{id}/score
    ▼
eligibility gate → RUL model (out-of-distribution check)
```

## Canonical schema — `plant-telemetry-v1`

| Field | Type | Required | Notes |
|---|---|---|---|
| `asset_id` | string | ✅ | Asset tag or equipment id |
| `cycle` | integer | ✅ | Monotonic operating cycle or run-hour index |
| `op1`, `op2`, `op3` | float | — | Operating settings; default 0 for scoring |
| `s1` … `s21` | float | — | Telemetry channels, C-MAPSS-compatible numbering |

Storage accepts a partial sensor set. The current RUL model does not: it needs
all 21 channels and at least 30 cycles, because its rolling features are built
from that contract.

## Mapping suggestions

Suggestions are advisory and always overridable. The matcher normalises a header
(case, spaces, punctuation) and checks, in order:

1. sensor patterns — `s3`, `sensor_3`, `Sensor-3`, `SENSOR 03` → `s3`;
2. exact aliases — `Engine ID`/`Unit Number`/`Machine` → `asset_id`,
   `Cycle`/`Operating Hours` → `cycle`, `T24` → `s3`, `Nf` → `s5`, `W32` → `s21`;
3. prefix/suffix aliases with lower confidence (0.7).

Ambiguous physical labels are deliberately **not** auto-mapped: C-MAPSS uses
`Ps30` for both s7 and s11, and `NRf`/`NRc` for two channels each. Mapping them
automatically would silently pick one; the operator must choose.

Every proposal reports its confidence and the API returns the unmapped list.

## Validation rules

Validation never mutates the source. It coerces mapped columns, reports every
problem with a severity, and computes a quality score (`100 − 15·errors −
3·warnings − 0.5·infos`).

**Blocking (readiness `blocked`, import refused)**

| Code | Meaning |
|---|---|
| `missing_required` | `asset_id` or `cycle` not mapped |
| `unknown_source` / `unknown_target` | mapping references a column or field that does not exist |
| `duplicate_target` | two source columns feed the same canonical field |
| `non_numeric` | mapped numeric column contains non-numeric values |
| `missing_keys` | rows without asset id or cycle |
| `duplicate_keys` | repeated `(asset_id, cycle)` |
| `invalid_cycle` | cycle below 1 |
| `missing_values` ≥ 20% | a mapped channel is mostly empty |

**Warnings (registered, but flagged)**

- missing values under 20% in a channel;
- gaps in the cycle sequence — the model never imputes them;
- negative values in a telemetry channel;
- fractional cycles (rounded);
- fewer than 30 cycles per asset (`short_history`);
- an asset arriving out of cycle order (sorted before storage, reported as info).

Constant channels are reported as info, not silently dropped.

## Readiness and the scoring gate

| State | Meaning |
|---|---|
| `ready` | No errors or warnings; passes the sensor/history contract |
| `warnings` | Stored, but at least one warning; scoring may still be blocked |
| `blocked` | Not stored; import returns 422 |

A registry entry is **score-eligible** only when the mapping has no errors, all
21 sensors are mapped and the asset has ≥ 30 cycles. `POST /onboarding/assets/{id}/score`
returns 422 with the exact reasons when any condition fails, and only then loads
the parquet and calls the RUL model.

The scoring response carries an explicit warning: the RUL model was trained on
NASA C-MAPSS FD001 simulated engines. A plant result is an out-of-distribution
check, not a validated prediction. Units and operating conditions must match the
training definition before the number means anything.

## Asset registry

`plant_assets` is keyed by canonical `asset_id` and upserts on re-import:

| Column | Content |
|---|---|
| `asset_id`, `name` | identity and display name |
| `source_file` | original filename |
| `mapping_json` | exact source → canonical mapping used |
| `sensors_json` | mapped sensor channels |
| `status`, `score_eligible` | readiness and the gate outcome |
| `rows`, `cycles`, `min_cycle`, `max_cycle` | coverage |
| `quality_json` | trimmed validation report |
| `parquet_path` | per-asset canonical data under `data/processed/plant/` |

Because the mapping is stored per asset, two assets can arrive from different
files with different column names and still be validated independently.

## API

```bash
# 1. inspect (raw CSV body)
curl -X POST "http://127.0.0.1:8000/api/v1/onboarding/inspect?filename=comp.csv" \
     -H "Content-Type: text/csv" --data-binary @comp.csv

# 2. validate a mapping (JSON)
curl -X POST http://127.0.0.1:8000/api/v1/onboarding/validate \
     -H "Content-Type: application/json" \
     -d '{"csv_text":"...","mapping":{"Engine ID":"asset_id","Cycle":"cycle","T24":"s3"}}'

# 3. import once validation is not blocked
curl -X POST http://127.0.0.1:8000/api/v1/onboarding/import \
     -H "Content-Type: application/json" \
     -d '{"name":"Compressor A","csv_text":"...","mapping":{...}}'

# 4. registry and the gated score
curl http://127.0.0.1:8000/api/v1/onboarding/assets
curl -X POST http://127.0.0.1:8000/api/v1/onboarding/assets/1/score
```

Limits: 5 MB per upload, 250,000 rows, delimiter sniffed from the file.

## What this prototype does not do

- **No live connector.** CSV files only; OPC-UA/MQTT/PLC ingestion is not
  implemented. The validation contract is the reusable part.
- **No unit conversion or timestamp parsing.** Cycles must already be numeric.
  A real deployment needs a units table and a time-partitioning step.
- **No per-asset model calibration.** Every onboarded asset is scored by the
  same C-MAPSS-trained RUL model; there is no fine-tuning or per-asset baseline.
- **No multi-tenancy or authorisation.** The registry is global; mutating
  endpoints share the optional API key.
- **Upsert by asset id.** Re-importing an asset replaces its parquet and
  metadata; historical versions of the same asset are not retained.
- **No automated mapping for ambiguous channels.** By design, but it means a
  large export may need manual work.
