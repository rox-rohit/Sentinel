"""Adapter package exports."""

from sentinel.data.adapters.registry import available_adapters, load_adapter, register_adapter
from sentinel.data.adapters.ai4i import AI4IAdapter
from sentinel.data.adapters.cmapss import CMAPSSAdapter

__all__ = [
    "AI4IAdapter",
    "CMAPSSAdapter",
    "available_adapters",
    "load_adapter",
    "register_adapter",
]
