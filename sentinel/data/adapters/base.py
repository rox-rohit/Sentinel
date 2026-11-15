"""Dataset adapter interface.

An adapter knows three things: where its raw files live, how to read them and
how to map them into the canonical frame. Nothing downstream knows the source
format.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from sentinel.data.schema import DatasetSchema


@dataclass
class AdapterInfo:
    name: str
    display_name: str
    source_url: str
    citation: str
    license_note: str
    task: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


class DatasetAdapter(abc.ABC):
    info: AdapterInfo
    schema: DatasetSchema

    @abc.abstractmethod
    def is_available(self) -> bool:
        """True when the raw files required by this adapter are present."""

    @abc.abstractmethod
    def load_raw(self) -> pd.DataFrame:
        """Read the raw source into a dataframe without inventing values."""

    @abc.abstractmethod
    def canonicalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Map the raw frame into the canonical column names/types."""

    def load(self) -> pd.DataFrame:
        return self.canonicalize(self.load_raw())

    def describe(self) -> dict:
        return {
            **self.info.__dict__,
            "available": self.is_available(),
            "schema": self.schema.to_dict(),
        }

    def raw_paths(self) -> list[Path]:
        return []
