"""Canonical dataset schema description.

Every adapter maps its source columns into a canonical frame described by a
`DatasetSchema`. Validation, feature engineering and the API only ever see the
canonical names, which is what lets new datasets plug in without changing the
rest of the platform.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: str  # float | int | category | datetime
    required: bool = True
    unit: str | None = None
    description: str = ""
    non_negative: bool = False


@dataclass(frozen=True)
class DatasetSchema:
    name: str
    columns: tuple[ColumnSpec, ...]
    id_column: str | None = None
    time_column: str | None = None
    target_columns: tuple[str, ...] = ()
    sensor_columns: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def by_name(self) -> dict[str, ColumnSpec]:
        return {c.name: c for c in self.columns}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "id_column": self.id_column,
            "time_column": self.time_column,
            "target_columns": list(self.target_columns),
            "sensor_columns": list(self.sensor_columns),
            "columns": [asdict(c) for c in self.columns],
            "notes": list(self.notes),
        }


def sensor_column(name: str, unit: str, description: str, non_negative: bool = False) -> ColumnSpec:
    return ColumnSpec(name=name, dtype="float", unit=unit, description=description,
                      non_negative=non_negative)
