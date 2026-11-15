"""Adapter registry: the only place that knows which datasets exist."""

from __future__ import annotations

from sentinel.data.adapters.ai4i import AI4IAdapter
from sentinel.data.adapters.base import DatasetAdapter
from sentinel.data.adapters.cmapss import CMAPSSAdapter

_ADAPTERS: dict[str, type[DatasetAdapter]] = {
    "cmapss": CMAPSSAdapter,
    "ai4i": AI4IAdapter,
}


def available_adapters() -> dict[str, type[DatasetAdapter]]:
    return dict(_ADAPTERS)


def load_adapter(name: str) -> DatasetAdapter:
    try:
        factory = _ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown dataset adapter {name!r}. Registered: {sorted(_ADAPTERS)}"
        ) from exc
    return factory()


def register_adapter(name: str, factory: type[DatasetAdapter]) -> None:
    """Extension point: integrate a new dataset without touching call sites."""
    _ADAPTERS[name] = factory
