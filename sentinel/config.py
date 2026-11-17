"""Typed configuration for the SENTINEL platform.

Every path and tunable lives here so that pipelines, the API and the exported
snapshot agree. Values may be overridden with `SENTINEL_*` environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
ARTIFACTS = ROOT / "artifacts"
MODEL_DIR = ARTIFACTS / "models"
META_DIR = ARTIFACTS / "meta"
GENERATED = ROOT / "src" / "generated"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _database_url() -> str:
    """Accept hosted Postgres URLs and route them through psycopg 3."""
    raw = os.environ.get(
        "SENTINEL_DATABASE_URL", f"sqlite:///{(ARTIFACTS / 'sentinel.db').as_posix()}"
    )
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://"):]
    return raw


def _cors_origins() -> tuple[str, ...]:
    defaults = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    )
    extra = os.environ.get("SENTINEL_CORS_ORIGINS", "")
    return tuple(dict.fromkeys(
        [*defaults, *(origin.strip() for origin in extra.split(",") if origin.strip())]
    ))


@dataclass(frozen=True)
class CostModel:
    """Explicit business assumptions.

    These are *assumptions* for scenario analysis, not measured plant figures.
    They are surfaced in the API payloads and the Maintenance Optimiser UI.
    """

    false_negative_cost: float = 500.0        # missed failure -> unplanned stop
    false_positive_cost: float = 50.0         # unnecessary inspection
    planned_maintenance_cost: float = 120.0   # parts + labour per planned service
    unplanned_failure_cost: float = 500.0     # includes secondary damage
    downtime_cost_per_hour: float = 900.0
    planned_downtime_hours: float = 4.0
    unplanned_downtime_hours: float = 18.0


@dataclass(frozen=True)
class HealthWeights:
    """Weights of the transparent health score (must sum to 1.0)."""

    rul: float = 0.45
    risk: float = 0.25
    anomaly: float = 0.20
    trend: float = 0.10

    def normalized(self) -> "HealthWeights":
        total = self.rul + self.risk + self.anomaly + self.trend
        return replace(self, rul=self.rul / total, risk=self.risk / total,
                       anomaly=self.anomaly / total, trend=self.trend / total)


@dataclass(frozen=True)
class Settings:
    # --- storage -----------------------------------------------------------
    database_url: str = field(default_factory=_database_url)
    model_dir: Path = MODEL_DIR
    meta_dir: Path = META_DIR
    artifacts_dir: Path = ARTIFACTS

    # --- datasets ----------------------------------------------------------
    primary_fleet_dataset: str = "cmapss"
    cmapss_subset: str = os.environ.get("SENTINEL_CMAPSS_SUBSET", "FD001")
    ai4i_filename: str = "ai4i/ai4i2020.csv"

    # --- leakage-safe feature engineering ---------------------------------
    rolling_windows: tuple[int, ...] = (5, 15, 30)
    rolling_stats: tuple[str, ...] = ("mean", "std", "min", "max")
    ema_spans: tuple[int, ...] = (10, 30)
    lags: tuple[int, ...] = (1, 5)

    # --- RUL ---------------------------------------------------------------
    rul_clip: int = _env_int("SENTINEL_RUL_CLIP", 125)
    healthy_cycle_limit: int = 30
    horizon_cycles: tuple[int, ...] = (10, 30, 50, 125)

    # --- modelling ---------------------------------------------------------
    random_seed: int = 42
    test_size: float = 0.25
    cv_folds: int = 5
    failure_target: str = "machine_failure"

    # --- decision ----------------------------------------------------------
    maintenance_budget: float = _env_float("SENTINEL_MAINTENANCE_BUDGET", 2500.0)
    criticality_default: int = 2  # 1 low, 2 medium, 3 high
    costs: CostModel = field(default_factory=CostModel)
    health_weights: HealthWeights = field(default_factory=HealthWeights)

    # --- api ---------------------------------------------------------------
    api_prefix: str = "/api/v1"
    cors_origins: tuple[str, ...] = field(default_factory=_cors_origins)
    # Hosted frontends can be added without rebuilding by setting this regex.
    cors_origin_regex: str = os.environ.get(
        "SENTINEL_CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1):\d+"
    )
    api_key: str | None = os.environ.get("SENTINEL_API_KEY") or None
    seed_db: str | None = os.environ.get("SENTINEL_SEED_DB") or None

    def ensure_dirs(self) -> None:
        for path in (DATA_PROCESSED, ARTIFACTS, MODEL_DIR, META_DIR, GENERATED):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
