"""Structured logging shared by pipelines and the API."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger("sentinel")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"sentinel.{name}")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


configure_logging()
