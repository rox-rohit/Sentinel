"""Model artifact persistence.

Artifacts are (model, metadata) pairs on disk. The registry is the metadata
store (SQLite/PostgreSQL) — see sentinel.store.db — while joblib files hold the
fitted estimators. Neither is committed to version control.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib

from sentinel.config import MODEL_DIR, META_DIR, settings
from sentinel.logging_setup import get_logger

log = get_logger("models.store")


@dataclass
class ModelArtifact:
    name: str
    task: str
    model: Any
    feature_names: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def save(self, directory: Path | None = None) -> Path:
        directory = directory or settings.model_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.name}.joblib"
        joblib.dump(
            {
                "model": self.model,
                "feature_names": self.feature_names,
                "metadata": self.metadata,
                "task": self.task,
            },
            path,
        )
        log.info("saved model artifact %s", path.name)
        return path


def load_artifact(name: str, directory: Path | None = None) -> ModelArtifact:
    directory = directory or MODEL_DIR
    path = directory / f"{name}.joblib"
    if not path.exists():
        raise FileNotFoundError(
            f"Model artifact {name!r} not found at {path}. Run: python -m sentinel.pipelines.build"
        )
    payload = joblib.load(path)
    return ModelArtifact(
        name=name,
        task=payload.get("task", "unknown"),
        model=payload["model"],
        feature_names=list(payload.get("feature_names", [])),
        metadata=dict(payload.get("metadata", {})),
    )


def write_meta(name: str, payload: dict) -> Path:
    settings.meta_dir.mkdir(parents=True, exist_ok=True)
    path = settings.meta_dir / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def read_meta(name: str) -> dict:
    path = settings.meta_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Metadata {name!r} missing at {path}. Run the build pipeline.")
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_exists(name: str) -> bool:
    return (MODEL_DIR / f"{name}.joblib").exists()
