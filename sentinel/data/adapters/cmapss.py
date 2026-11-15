"""NASA C-MAPSS turbofan degradation adapter.

Raw files are whitespace-separated, 26 columns, no header:
  unit, cycle, op1..op3, s1..s21

Training trajectories run to failure (RUL = last cycle - cycle). Test
trajectories stop before failure and the official RUL file gives the true
remaining life at the final recorded cycle of each unit.

This adapter is deliberately lossless: cyclic sensor and operating-setting
columns are preserved, and dataset-specific quirks stay inside this module.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sentinel.config import DATA_RAW, settings
from sentinel.data.adapters.base import AdapterInfo, DatasetAdapter
from sentinel.data.schema import ColumnSpec, DatasetSchema, sensor_column

SUBSETS = ("FD001", "FD002", "FD003", "FD004")

# NASA C-MAPSS sensor channel descriptions (Saxena & Goebel, 2008).
SENSOR_LABELS = {
    "s1": "Fan inlet temperature (T2)",
    "s2": "Fan inlet pressure (P2)",
    "s3": "LPC outlet temperature (T24)",
    "s4": "LPC outlet pressure (P24)",
    "s5": "Fan speed (Nf)",
    "s6": "Core speed (Nc)",
    "s7": "HPC outlet static pressure (Ps30)",
    "s8": "Fuel flow ratio (phi)",
    "s9": "Corrected fan speed (NRf)",
    "s10": "Corrected core speed (NRc)",
    "s11": "HPC outlet static pressure (Ps30)",
    "s12": "LPT outlet temperature (T50)",
    "s13": "Corrected fan speed (NRf)",
    "s14": "Corrected core speed (NRc)",
    "s15": "Bypass ratio (BPR)",
    "s16": "Burner fuel-air ratio (farB)",
    "s17": "Bleed enthalpy (htBleed)",
    "s18": "Demanded fan speed (Nf_dmd)",
    "s19": "Demanded corrected fan speed",
    "s20": "HPT coolant bleed (W31)",
    "s21": "LPT coolant bleed (W32)",
}

# Channels that are constant across the whole FD001 training set and therefore
# carry no information. Verified by validation; listed here for documentation.
CONSTANT_FD001 = ("s1", "s5", "s10", "s16", "s18", "s19")

RAW_COLUMNS = (
    ["unit", "cycle", "op1", "op2", "op3"] + [f"s{i}" for i in range(1, 22)]
)

SENSOR_COLUMNS = tuple(f"s{i}" for i in range(1, 22))


class CMAPSSAdapter(DatasetAdapter):
    info = AdapterInfo(
        name="cmapss",
        display_name="NASA C-MAPSS Turbofan Engine Degradation",
        source_url="https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data",
        citation=(
            "A. Saxena, K. Goebel, D. Simon, N. Eklund, 'Damage Propagation Modeling for "
            "Aircraft Engine Run-to-Failure Simulation', PHM 2008. NASA PCoE repository."
        ),
        license_note="NASA Open Data Portal; retain attribution to NASA PCoE.",
        task=["rul_regression", "anomaly_detection", "degradation", "maintenance"],
        limitations=[
            "Simulated turbofan engines, not a factory asset.",
            "Sensor units are simulated physical quantities; do not mix with other datasets.",
            "FD001 has one operating condition and one fault mode; FD002/FD004 have six "
            "conditions, which needs condition normalisation to generalise.",
            "Trajectories end at failure, so RUL targets above the clip horizon are uninformative.",
        ],
    )
    schema = DatasetSchema(
        name="cmapss",
        columns=(
            ColumnSpec("asset_id", "int", non_negative=True, description="Engine unit number"),
            ColumnSpec("cycle", "int", non_negative=True, description="Operational cycle"),
            sensor_column("op1", "", "Operational setting 1"),
            sensor_column("op2", "", "Operational setting 2"),
            sensor_column("op3", "", "Operational setting 3"),
            *[sensor_column(s, "", SENSOR_LABELS[s]) for s in SENSOR_COLUMNS],
        ),
        id_column="asset_id",
        time_column="cycle",
        target_columns=("rul",),
        sensor_columns=SENSOR_COLUMNS,
        notes=("Time series per engine; official test set has RUL labels per unit.",),
    )

    def __init__(self, root=None, subset: str | None = None) -> None:
        self.root = root or (DATA_RAW / "cmapss")
        self.subset = subset or settings.cmapss_subset
        if self.subset not in SUBSETS:
            raise ValueError(f"Unknown C-MAPSS subset {self.subset!r}; expected one of {SUBSETS}")

    # -- paths ------------------------------------------------------------
    def raw_paths(self):
        folder = self._folder()
        return [folder / f"{prefix}_{self.subset}.txt" for prefix in ("train", "test", "RUL")]

    def _folder(self):
        direct = self.root / f"train_{self.subset}.txt"
        return self.root if direct.exists() else self.root / "CMAPSSData"

    def is_available(self) -> bool:
        return all(p.exists() for p in self.raw_paths())

    # -- reading ----------------------------------------------------------
    def _read(self, path) -> pd.DataFrame:
        if not path.exists():
            raise FileNotFoundError(f"Missing C-MAPSS file: {path}. Run: python scripts/fetch_data.py")
        df = pd.read_csv(path, sep=r"\s+", header=None, names=RAW_COLUMNS, engine="python")
        return df.dropna(how="all")

    def load_raw(self) -> pd.DataFrame:
        df = self._read(self._folder() / f"train_{self.subset}.txt")
        df["split"] = "train"
        return df

    def load_test(self) -> pd.DataFrame:
        df = self._read(self._folder() / f"test_{self.subset}.txt")
        df["split"] = "test"
        return df

    def load_rul_labels(self) -> pd.Series:
        path = self._folder() / f"RUL_{self.subset}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Missing C-MAPSS RUL labels: {path}")
        values = pd.read_csv(path, header=None, names=["rul"]).squeeze("columns").astype(float)
        values.index = np.arange(1, len(values) + 1)
        values.index.name = "asset_id"
        return values

    # -- canonical mapping -------------------------------------------------
    def canonicalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        df = raw.rename(columns={"unit": "asset_id"}).copy()
        df["asset_id"] = df["asset_id"].astype(int)
        df["cycle"] = df["cycle"].astype(int)
        numeric = ["op1", "op2", "op3", *SENSOR_COLUMNS]
        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        if "split" in df.columns:
            df["split"] = df["split"].astype(str)

        if "rul" not in df.columns:
            if "split" in df.columns and (df["split"] == "test").all():
                # Test trajectories: official RUL applies to the final cycle only.
                last = df.groupby("asset_id")["cycle"].transform("max")
                official = self.load_rul_labels()
                df["rul"] = np.where(
                    df["cycle"] == last,
                    df["asset_id"].map(official).astype(float),
                    np.nan,
                )
            else:
                last = df.groupby("asset_id")["cycle"].transform("max")
                df["rul"] = (last - df["cycle"]).astype(float)
        df = df.sort_values(["asset_id", "cycle"]).reset_index(drop=True)
        return df

    def load_all(self) -> pd.DataFrame:
        """Train + official test rows with RUL labels where defined."""
        train = self.load()
        test = self.canonicalize(self.load_test())
        return pd.concat([train, test], ignore_index=True)
