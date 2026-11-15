"""UCI AI4I 2020 Predictive Maintenance adapter.

Source: UCI Machine Learning Repository, dataset 601 (AI4I 2020).
10,000 synthetic-but-physically-informed milling-process records with five
labelled failure modes. No timestamps: rows are independent process steps, so
this adapter is for tabular supervised learning only, never for fleet timelines.
"""

from __future__ import annotations

import pandas as pd

from sentinel.config import DATA_RAW, settings
from sentinel.data.adapters.base import AdapterInfo, DatasetAdapter
from sentinel.data.schema import ColumnSpec, DatasetSchema, sensor_column

SOURCE_COLUMNS = {
    "UDI": "row_id",
    "Product ID": "asset_id",
    "Type": "product_type",
    "Air temperature [K]": "air_temp_k",
    "Process temperature [K]": "process_temp_k",
    "Rotational speed [rpm]": "rotational_speed_rpm",
    "Torque [Nm]": "torque_nm",
    "Tool wear [min]": "tool_wear_min",
    "Machine failure": "machine_failure",
    "TWF": "failure_twf",
    "HDF": "failure_hdf",
    "PWF": "failure_pwf",
    "OSF": "failure_osf",
    "RNF": "failure_rnf",
}

FAILURE_MODES = (
    ("failure_twf", "Tool wear failure"),
    ("failure_hdf", "Heat dissipation failure"),
    ("failure_pwf", "Power failure"),
    ("failure_osf", "Overstrain failure"),
    ("failure_rnf", "Random failure"),
)


class AI4IAdapter(DatasetAdapter):
    info = AdapterInfo(
        name="ai4i",
        display_name="UCI AI4I 2020 Predictive Maintenance",
        source_url="https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset",
        citation=(
            "S. Matzka, 'Explainable Artificial Intelligence for Predictive Maintenance "
            "Applications', PHM Asia Pacific 2020. Dataset via UCI ML Repository."
        ),
        license_note="CC BY 4.0 (UCI ML Repository).",
        task=["failure_classification", "failure_mode_classification", "explainability"],
        limitations=[
            "Synthetic milling-process simulation, not a real production line.",
            "Rows are independent process steps: no time ordering or machine continuity.",
            "Random failures (RNF, 19 rows) are too rare for reliable modelling.",
            "Failure modes overlap; the Machine failure label is the union of the five modes.",
        ],
    )
    schema = DatasetSchema(
        name="ai4i",
        columns=(
            ColumnSpec("row_id", "int", non_negative=True, description="Process-step row identifier (UDI)"),
            ColumnSpec("asset_id", "category", description="Product identifier of the processed part"),
            ColumnSpec("product_type", "category", description="Product quality variant L/M/H"),
            sensor_column("air_temp_k", "K", "Ambient air temperature", True),
            sensor_column("process_temp_k", "K", "Process temperature", True),
            sensor_column("rotational_speed_rpm", "rpm", "Spindle rotational speed", True),
            sensor_column("torque_nm", "Nm", "Spindle torque"),
            sensor_column("tool_wear_min", "min", "Accumulated tool wear", True),
            ColumnSpec("machine_failure", "int", non_negative=True, description="Any failure occurred"),
            ColumnSpec("failure_twf", "int", non_negative=True, description="Tool wear failure"),
            ColumnSpec("failure_hdf", "int", non_negative=True, description="Heat dissipation failure"),
            ColumnSpec("failure_pwf", "int", non_negative=True, description="Power failure"),
            ColumnSpec("failure_osf", "int", non_negative=True, description="Overstrain failure"),
            ColumnSpec("failure_rnf", "int", non_negative=True, description="Random failure"),
        ),
        id_column="asset_id",
        time_column=None,
        target_columns=("machine_failure",),
        sensor_columns=(
            "air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min",
        ),
        notes=("Tabular: no time axis, no per-machine continuity.",),
    )

    def __init__(self, path=None) -> None:
        self.path = path or (DATA_RAW / settings.ai4i_filename)

    def raw_paths(self):
        return [self.path]

    def is_available(self) -> bool:
        return self.path.exists()

    def load_raw(self) -> pd.DataFrame:
        if not self.is_available():
            raise FileNotFoundError(
                f"AI4I raw dataset not found at {self.path}. Run: python scripts/fetch_data.py"
            )
        return pd.read_csv(self.path, encoding="utf-8-sig")

    def canonicalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in SOURCE_COLUMNS if c not in raw.columns]
        if missing:
            raise ValueError(f"AI4I source is missing expected columns: {missing}")
        df = raw.rename(columns=SOURCE_COLUMNS).copy()
        df["row_id"] = df["row_id"].astype(int)
        df["asset_id"] = df["asset_id"].astype("category")
        df["product_type"] = df["product_type"].astype("category")
        for col in (
            "air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min",
        ):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        for col in ("machine_failure", "failure_twf", "failure_hdf", "failure_pwf",
                    "failure_osf", "failure_rnf"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int8")
        return df
