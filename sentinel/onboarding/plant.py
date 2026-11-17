"""Real-plant onboarding: canonical schema, column mapping and validation.

The research adapters know their own file formats. A customer CSV does not, so
this module asks for an explicit column mapping into the canonical telemetry
schema and validates the mapped frame before anything is stored or scored.

Nothing here trains or predicts. Validation returns a report; the import step
refuses blocked data, and the scoring gate refuses assets that do not satisfy
the model's feature contract.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

from sentinel.data.schema import ColumnSpec, DatasetSchema

SCHEMA_VERSION = "plant-telemetry-v1"
MAX_CYCLES_FOR_SCORING = 30
SENSORS = tuple(f"s{i}" for i in range(1, 22))

PLANT_SCHEMA = DatasetSchema(
    name="plant_telemetry",
    columns=(
        ColumnSpec("asset_id", "str", description="Asset identifier or tag"),
        ColumnSpec("cycle", "int", non_negative=True,
                   description="Monotonic operating cycle or run-hour index"),
        ColumnSpec("op1", "float", required=False, description="Operating setting 1"),
        ColumnSpec("op2", "float", required=False, description="Operating setting 2"),
        ColumnSpec("op3", "float", required=False, description="Operating setting 3"),
        *[
            ColumnSpec(f"s{i}", "float", required=False,
                       description=f"Telemetry channel s{i}")
            for i in range(1, 22)
        ],
    ),
    id_column="asset_id",
    time_column="cycle",
    sensor_columns=SENSORS,
    notes=(
        "One row per asset per cycle. Column names are the customer's; the "
        "mapping decides which canonical field each one feeds.",
        "Sensors are optional for storage, but scoring requires all 21 channels "
        "and at least 30 cycles for the current RUL model.",
    ),
)

REQUIRED_TARGETS = ("asset_id", "cycle")
TARGETS = tuple(column.name for column in PLANT_SCHEMA.columns)

# Normalised aliases. Ambiguous physical labels (Ps30, NRf, NRc) are omitted
# because C-MAPSS maps two channels to each of them.
_ALIASES: dict[str, tuple[str, ...]] = {
    "asset_id": ("assetid", "asset", "unit", "unitid", "unitnumber", "engine",
                 "engineid", "machine", "machineid", "equipment", "equipmentid",
                 "tag", "tagid", "deviceid", "serial", "serialnumber"),
    "cycle": ("cycle", "cycles", "cycleno", "step", "timeindex", "index",
              "operatingcycle", "runtime", "hours", "operatinghours"),
    "op1": ("op1", "setting1", "operationalsetting1", "ops1"),
    "op2": ("op2", "setting2", "operationalsetting2", "ops2"),
    "op3": ("op3", "setting3", "operationalsetting3", "ops3"),
    "s1": ("s1", "t2", "faninlettemperature"),
    "s2": ("s2", "p2", "faninletpressure"),
    "s3": ("s3", "t24", "lpcoutlettemperature"),
    "s4": ("s4", "p24", "lpcoutletpressure"),
    "s5": ("s5", "nf", "fanspeed"),
    "s6": ("s6", "nc", "corespeed"),
    "s7": ("s7",),
    "s8": ("s8", "phi", "fuelflowratio"),
    "s9": ("s9",),
    "s10": ("s10",),
    "s11": ("s11",),
    "s12": ("s12", "t50", "lptoutlettemperature"),
    "s13": ("s13",),
    "s14": ("s14",),
    "s15": ("s15", "bpr", "bypassratio"),
    "s16": ("s16", "farb", "burnerfuelairratio"),
    "s17": ("s17", "htbleed", "bleedenthalpy"),
    "s18": ("s18", "nfdmd", "demandedfanspeed"),
    "s19": ("s19", "demandedcorrectedfanspeed"),
    "s20": ("s20", "w31", "hptcoolantbleed"),
    "s21": ("s21", "w32", "lptcoolantbleed"),
}

_SENSOR_PATTERN = re.compile(r"^s(?:ensor)?[_\-\s]?0*(\d{1,2})$")


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def suggest_target(column: str) -> tuple[str | None, float]:
    """Propose a canonical target for a customer column, with a confidence."""
    normalised = _normalise(column)
    match = _SENSOR_PATTERN.match(column.strip().lower())
    if match:
        index = int(match.group(1))
        if 1 <= index <= 21:
            return f"s{index}", 0.95
    for target, aliases in _ALIASES.items():
        if normalised in aliases:
            return target, 1.0
    for target, aliases in _ALIASES.items():
        for alias in aliases:
            if len(alias) >= 4 and (normalised.startswith(alias) or normalised.endswith(alias)):
                return target, 0.7
    return None, 0.0


def schema_payload() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "schema": PLANT_SCHEMA.to_dict(),
        "required_targets": list(REQUIRED_TARGETS),
        "targets": list(TARGETS),
        "sensors": list(SENSORS),
        "min_cycles_for_scoring": MAX_CYCLES_FOR_SCORING,
        "aliases": {target: list(aliases) for target, aliases in _ALIASES.items()},
        "limits": {"max_upload_bytes": 5 * 1024 * 1024, "max_rows": 250_000},
    }


def parse_csv(text: str) -> pd.DataFrame:
    """Parse a customer CSV, sniffing the delimiter; never mutate columns."""
    if not text.strip():
        raise ValueError("CSV is empty.")
    try:
        frame = pd.read_csv(io.StringIO(text), sep=None, engine="python")
    except Exception:
        frame = pd.read_csv(io.StringIO(text))
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("CSV has no data rows or no columns.")
    frame.columns = [str(column).strip() for column in frame.columns]
    if any(not column for column in frame.columns):
        raise ValueError("CSV contains an unnamed column.")
    return frame


def inspect_frame(frame: pd.DataFrame) -> dict:
    columns = []
    for name in frame.columns:
        target, confidence = suggest_target(name)
        series = frame[name]
        sample = [
            None if pd.isna(value) else value.item() if hasattr(value, "item") else value
            for value in series.head(3)
        ]
        columns.append({
            "source": name,
            "target": target,
            "confidence": confidence,
            "dtype": str(series.dtype),
            "missing_pct": round(float(series.isna().mean() * 100), 2),
            "unique": int(series.nunique(dropna=True)),
            "sample": sample,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "rows": int(len(frame)),
        "columns": columns,
        "suggested_mapping": {
            entry["source"]: entry["target"] for entry in columns if entry["target"]
        },
        "unmapped": [entry["source"] for entry in columns if not entry["target"]],
        "required_targets": list(REQUIRED_TARGETS),
        "targets": list(TARGETS),
    }


def _issue(severity: str, code: str, message: str, column: str | None = None,
           count: int = 0, pct: float = 0.0) -> dict:
    return {"severity": severity, "code": code, "message": message, "column": column,
            "count": int(count), "pct": round(float(pct), 3)}


def apply_mapping(frame: pd.DataFrame, mapping: dict[str, str]) -> tuple[pd.DataFrame, list[dict]]:
    """Rename and coerce mapped columns; coercion failures become missing values."""
    issues: list[dict] = []
    cleaned = {source: target for source, target in mapping.items()
               if target and target != "ignore"}
    for source, target in cleaned.items():
        if source not in frame.columns:
            issues.append(_issue("error", "unknown_source",
                                 f"Mapped column {source!r} does not exist in the file.", source))
        if target not in TARGETS:
            issues.append(_issue("error", "unknown_target",
                                 f"Target {target!r} is not in the canonical schema.", source))
    targets = [target for target in cleaned.values() if target in TARGETS]
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        issues.append(_issue("error", "duplicate_target",
                             f"Several columns map to the same field: {duplicates}."))
    missing_required = [target for target in REQUIRED_TARGETS if target not in targets]
    if missing_required:
        issues.append(_issue("error", "missing_required",
                             f"Required fields are not mapped: {missing_required}."))
        return pd.DataFrame(), issues

    canonical = pd.DataFrame(index=frame.index)
    for source, target in cleaned.items():
        if source not in frame.columns or target not in TARGETS:
            continue
        series = frame[source]
        if target == "asset_id":
            canonical[target] = series.astype("string").str.strip()
        elif target == "cycle":
            numeric = pd.to_numeric(series, errors="coerce")
            failures = int(numeric.isna().sum() - series.isna().sum())
            if failures > 0:
                issues.append(_issue("error", "non_numeric",
                                     f"{failures} cycle value(s) are not numeric.", target, failures))
            fractional = int(((numeric.dropna() % 1) != 0).sum())
            if fractional:
                issues.append(_issue("warning", "fractional_cycle",
                                     f"{fractional} cycle value(s) are fractional and will be rounded.",
                                     target, fractional))
            canonical[target] = numeric.round().astype("Int64")
        else:
            numeric = pd.to_numeric(series, errors="coerce")
            failures = int(numeric.isna().sum() - series.isna().sum())
            if failures > 0:
                issues.append(_issue("error", "non_numeric",
                                     f"{failures} value(s) are not numeric.", target, failures))
            canonical[target] = numeric.astype("float64")
    return canonical, issues


def _per_asset(canonical: pd.DataFrame, column: str) -> dict[str, float]:
    return canonical.groupby("asset_id")[column].max().to_dict()


def validate_canonical(canonical: pd.DataFrame, mapping: dict[str, str],
                       issues: list[dict], source_file: str = "upload") -> dict:
    issues = list(issues)
    if canonical.empty:
        return {
            "readiness": "blocked",
            "quality_score": 0.0,
            "rows": 0,
            "asset_count": 0,
            "assets": [],
            "issues": issues,
            "scoring": {"eligible": False, "reasons": ["No usable rows."],
                        "mapped_sensors": 0, "missing_sensors": list(SENSORS)},
            "mapping": mapping,
            "schema_version": SCHEMA_VERSION,
            "source_file": source_file,
        }

    keyed = canonical.dropna(subset=["asset_id", "cycle"]).copy()
    dropped = len(canonical) - len(keyed)
    if dropped:
        issues.append(_issue("error", "missing_keys",
                             f"{dropped} row(s) have no asset id or cycle and were excluded.", count=dropped))

    duplicates = int(keyed.duplicated(subset=["asset_id", "cycle"]).sum())
    if duplicates:
        issues.append(_issue("error", "duplicate_keys",
                             f"{duplicates} duplicated (asset_id, cycle) key(s).", count=duplicates))

    reordered = 0
    for _, group in keyed.groupby("asset_id", sort=False):
        if not group["cycle"].is_monotonic_increasing:
            reordered += 1
    if reordered:
        issues.append(_issue("info", "rows_reordered",
                             f"{reordered} asset(s) arrived out of cycle order; rows are sorted before storage.",
                             count=reordered))

    gaps = 0
    for _, group in keyed.groupby("asset_id"):
        cycles = np.sort(group["cycle"].astype(float).to_numpy())
        if len(cycles) > 1:
            gaps += int(np.sum(np.diff(cycles) != 1))
    if gaps:
        issues.append(_issue("warning", "time_gaps",
                             f"{gaps} missing cycle(s) between recorded rows; the model does not impute them.",
                             "cycle", gaps))

    negative_cycles = int((keyed["cycle"] < 1).sum())
    if negative_cycles:
        issues.append(_issue("error", "invalid_cycle",
                             f"{negative_cycles} row(s) have a cycle below 1.", "cycle", negative_cycles))

    mapped_sensors = [sensor for sensor in SENSORS if sensor in canonical.columns]
    for target in REQUIRED_TARGETS:
        if target not in canonical.columns:
            issues.append(_issue("error", "missing_required",
                                 f"{target} is absent from the mapped frame.", target))
    for column in [*mapped_sensors, "op1", "op2", "op3"]:
        if column not in canonical.columns:
            continue
        missing = int(keyed[column].isna().sum())
        if missing:
            pct = missing / len(keyed) * 100
            severity = "error" if pct >= 20 else "warning"
            issues.append(_issue(severity, "missing_values",
                                 f"{column}: {missing} missing value(s) after mapping ({pct:.1f}%).",
                                 column, missing, pct))
        if len(mapped_sensors) and column in mapped_sensors:
            unique = int(keyed[column].nunique(dropna=True))
            if unique <= 1:
                issues.append(_issue("info", "constant_column",
                                     f"{column} is constant and carries no information.", column))
            negatives = int((keyed[column] < 0).sum())
            if negatives:
                issues.append(_issue("warning", "negative_values",
                                     f"{column}: {negatives} negative value(s).", column, negatives))

    per_asset = keyed.groupby("asset_id")["cycle"].agg(["min", "max", "count"])
    assets = [
        {
            "asset_id": str(asset_id),
            "rows": int(row["count"]),
            "min_cycle": int(row["min"]),
            "max_cycle": int(row["max"]),
            "span": int(row["max"] - row["min"] + 1),
            "short_history": bool(row["count"] < MAX_CYCLES_FOR_SCORING),
        }
        for asset_id, row in per_asset.iterrows()
    ]
    short = [asset["asset_id"] for asset in assets if asset["short_history"]]
    if short:
        issues.append(_issue("warning", "short_history",
                             f"{len(short)} asset(s) have fewer than {MAX_CYCLES_FOR_SCORING} cycles; "
                             "they can be stored but not scored.", count=len(short)))

    missing_sensors = [sensor for sensor in SENSORS if sensor not in mapped_sensors]
    reasons: list[str] = []
    if any(issue["severity"] == "error" for issue in issues):
        reasons.append("Validation has blocking errors.")
    if missing_sensors:
        reasons.append(f"Scoring needs all 21 sensors; {len(missing_sensors)} are not mapped.")
    if short:
        reasons.append(f"{len(short)} asset(s) have less than {MAX_CYCLES_FOR_SCORING} cycles.")
    eligible = not reasons

    penalties = sum({"error": 15.0, "warning": 3.0, "info": 0.5}.get(issue["severity"], 0.0)
                    for issue in issues)
    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    readiness = "blocked" if errors else "warnings" if warnings else "ready"

    preview = keyed.sort_values(["asset_id", "cycle"]).head(5)
    preview_rows = [
        {key: (None if pd.isna(value) else value.item() if hasattr(value, "item") else value)
         for key, value in row.items()}
        for row in preview.to_dict(orient="records")
    ]

    return {
        "readiness": readiness,
        "quality_score": round(max(0.0, 100.0 - penalties), 1),
        "rows": int(len(keyed)),
        "asset_count": len(assets),
        "assets": assets,
        "issues": issues,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "scoring": {
            "eligible": eligible,
            "reasons": reasons,
            "mapped_sensors": len(mapped_sensors),
            "missing_sensors": missing_sensors,
            "min_cycles_required": MAX_CYCLES_FOR_SCORING,
        },
        "mapping": {source: target for source, target in mapping.items() if target and target != "ignore"},
        "schema_version": SCHEMA_VERSION,
        "source_file": source_file,
        "preview": preview_rows,
        "canonical_columns": [column.name for column in PLANT_SCHEMA.columns
                              if column.name in canonical.columns],
        "notes": list(PLANT_SCHEMA.notes),
    }


def validate_csv(text: str, mapping: dict[str, str], *, source_file: str = "upload") -> dict:
    frame = parse_csv(text)
    canonical, issues = apply_mapping(frame, mapping)
    report = validate_canonical(canonical, mapping, issues, source_file=source_file)
    report["source_columns"] = [str(column) for column in frame.columns]
    return report


def canonical_frame(text: str, mapping: dict[str, str]) -> pd.DataFrame:
    frame = parse_csv(text)
    canonical, _ = apply_mapping(frame, mapping)
    canonical = canonical.dropna(subset=["asset_id", "cycle"])
    canonical["asset_id"] = canonical["asset_id"].astype(str)
    canonical["cycle"] = canonical["cycle"].astype(int)
    return canonical.sort_values(["asset_id", "cycle"]).reset_index(drop=True)
