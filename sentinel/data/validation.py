"""Dataset validation and data-quality reporting.

Validation never mutates data and never raises on a quality problem: it returns
a report with per-issue severity. Pipelines decide what is blocking (schema
errors) and what is acceptable (documented warnings).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from sentinel.data.schema import DatasetSchema

SEVERITY_WEIGHT = {"error": 15.0, "warning": 3.0, "info": 0.5}


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    column: str | None = None
    count: int = 0
    pct: float = 0.0


@dataclass
class QualityReport:
    dataset: str
    rows: int
    columns: int
    issues: list[Issue] = field(default_factory=list)
    generated_at: str = ""

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def score(self) -> float:
        penalty = sum(SEVERITY_WEIGHT.get(i.severity, 0.0) for i in self.issues)
        return round(max(0.0, 100.0 - penalty), 1)

    def add(self, severity: str, code: str, message: str, column: str | None = None,
            count: int = 0, pct: float = 0.0) -> None:
        self.issues.append(Issue(severity, code, message, column, int(count), round(float(pct), 3)))

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "rows": self.rows,
            "columns": self.columns,
            "score": self.score,
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [asdict(i) for i in self.issues],
            "generated_at": self.generated_at,
        }


def _outlier_count(series: pd.Series) -> int:
    clean = series.dropna()
    if len(clean) < 20:
        return 0
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return 0
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((clean < low) | (clean > high)).sum())


def validate_dataset(df: pd.DataFrame, schema: DatasetSchema) -> QualityReport:
    report = QualityReport(
        dataset=schema.name,
        rows=int(len(df)),
        columns=int(df.shape[1]),
        generated_at=pd.Timestamp.utcnow().isoformat(),
    )
    specs = schema.by_name()

    if df.empty:
        report.add("error", "empty_dataset", "Dataset contains no rows.")
        return report

    # --- schema presence ---------------------------------------------------
    missing_required = [c.name for c in schema.columns if c.required and c.name not in df.columns]
    if missing_required:
        report.add("error", "missing_columns",
                   f"Required canonical columns are absent: {missing_required}",
                   count=len(missing_required))
    extra = [c for c in df.columns if c not in specs]
    if extra:
        report.add("info", "extra_columns",
                   f"{len(extra)} column(s) outside the canonical schema: {extra[:8]}", count=len(extra))

    present = [c for c in specs if c in df.columns]

    # --- dtype checks ------------------------------------------------------
    for name in present:
        spec = specs[name]
        if spec.dtype in {"float", "int"} and not pd.api.types.is_numeric_dtype(df[name]):
            report.add("error", "dtype_mismatch",
                       f"{name} must be numeric ({spec.dtype}).", column=name)
        if spec.dtype == "datetime" and not pd.api.types.is_datetime64_any_dtype(df[name]):
            report.add("error", "dtype_mismatch", f"{name} must be datetime.", column=name)

    # --- missing values ----------------------------------------------------
    total_cells = len(df) * max(1, len(present))
    for name in present:
        missing = int(df[name].isna().sum())
        if missing:
            pct = missing / len(df) * 100
            severity = "warning" if pct < 20 else "error"
            report.add(severity, "missing_values",
                       f"{name}: {missing} missing values ({pct:.1f}%).",
                       column=name, count=missing, pct=pct)
    if not any(i.code == "missing_values" for i in report.issues):
        report.add("info", "no_missing", "No missing values in canonical columns.", count=total_cells)

    # --- duplicates --------------------------------------------------------
    dup_rows = int(df.duplicated().sum())
    if dup_rows:
        report.add("warning", "duplicate_rows", f"{dup_rows} fully duplicated rows.",
                   count=dup_rows, pct=dup_rows / len(df) * 100)

    key_cols = [c for c in (schema.id_column, schema.time_column) if c and c in df.columns]
    if len(key_cols) == 2:
        dup_keys = int(df.duplicated(subset=key_cols).sum())
        if dup_keys:
            report.add("error", "duplicate_keys",
                       f"{dup_keys} duplicated ({key_cols[0]}, {key_cols[1]}) keys.",
                       count=dup_keys)
        gaps = []
        for _, group in df.groupby(key_cols[0], sort=False):
            cycles = np.sort(group[key_cols[1]].to_numpy())
            if len(cycles) > 1 and np.any(np.diff(cycles) != 1):
                gaps.append(int(np.sum(np.diff(cycles) != 1)))
        if gaps:
            report.add("warning", "time_gaps",
                       f"{len(gaps)} trajectory/trajectories have non-contiguous cycles.",
                       column=key_cols[1], count=sum(gaps))
        unsorted = 0
        for _, group in df.groupby(key_cols[0], sort=False):
            if not group[key_cols[1]].is_monotonic_increasing:
                unsorted += 1
        if unsorted:
            report.add("error", "time_not_monotonic",
                       f"{unsorted} trajectory/trajectories are not ordered by time.", count=unsorted)

    # --- constant / near-constant columns ---------------------------------
    for name in schema.sensor_columns:
        if name in df.columns and df[name].nunique(dropna=True) <= 1:
            report.add("info", "constant_column",
                       f"{name} is constant and carries no information.", column=name)

    # --- outliers and impossible values -----------------------------------
    outlier_total = 0
    for name in schema.sensor_columns:
        if name not in df.columns or not pd.api.types.is_numeric_dtype(df[name]):
            continue
        count = _outlier_count(df[name])
        outlier_total += count
        if count:
            report.add("info", "outliers",
                       f"{name}: {count} IQR outliers ({count / len(df) * 100:.1f}%).",
                       column=name, count=count, pct=count / len(df) * 100)
        spec = specs[name]
        if spec.non_negative:
            negatives = int((df[name] < 0).sum())
            if negatives:
                report.add("warning", "negative_values",
                           f"{name}: {negatives} negative values in a non-negative channel.",
                           column=name, count=negatives)
    if outlier_total:
        report.add("info", "outlier_summary",
                   f"{outlier_total} sensor values fall outside 1.5x IQR fences; "
                   "they are flagged, not removed.", count=outlier_total)

    # --- target sanity -----------------------------------------------------
    for target in schema.target_columns:
        if target not in df.columns:
            continue
        series = df[target].dropna()
        if series.nunique() == 1 and target in {"machine_failure"}:
            report.add("error", "single_class_target", f"{target} has a single class.", column=target)
        elif target == "machine_failure":
            positives = int(series.sum())
            report.add("info", "target_balance",
                       f"{target}: {positives}/{len(series)} positives ({positives / len(series) * 100:.2f}%).",
                       column=target, count=positives, pct=positives / len(series) * 100)
        elif target == "rul":
            report.add("info", "target_range",
                       f"rul ranges {float(series.min()):.0f}..{float(series.max()):.0f}.",
                       column=target)

    return report
