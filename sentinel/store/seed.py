"""Seed a hosted operational store from the build's local SQLite registry.

The image builds the pipeline once, which registers datasets, models and the
demo alert set in ``artifacts/sentinel.db``. At container start this module copies
that derived metadata into Postgres if the target is empty, so a fresh hosted
deployment shows the same registry and alert inbox as the build without
retraining or committing any binary artifacts.

    SENTINEL_SEED_DB=artifacts/sentinel.db python -m sentinel.store.seed

It is idempotent: a target that already has datasets/models is left untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from sentinel.config import ARTIFACTS, settings
from sentinel.store.db import AlertRecord, Base, DatasetRecord, ModelRecord

SEED_TABLES = (DatasetRecord, ModelRecord, AlertRecord)


def _source_url(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if not candidate.exists():
        return None
    return f"sqlite:///{candidate.as_posix()}"


def _portable_path(name: str, value: str) -> str:
    """Rewrite build-host paths to this deployment's artifact locations."""
    if not value:
        return value
    filename = Path(value).name
    if name == "artifact_path":
        return str(settings.model_dir / filename)
    if name == "path":
        return str(settings.artifacts_dir.parent / "data" / "processed" / filename)
    return value


def _copy_rows(source: Session, target: Session, model) -> int:
    rows = source.scalars(select(model)).all()
    columns = [column.name for column in model.__table__.columns if column.name != "id"]
    for row in rows:
        values = {name: getattr(row, name) for name in columns}
        for name in ("artifact_path", "path"):
            if name in values:
                values[name] = _portable_path(name, values[name])
        target.add(model(**values))
    return len(rows)


def seed_from_sqlite(source_path: str | Path | None = None,
                     target_url: str | None = None) -> dict:
    source_url = _source_url(source_path or settings.seed_db)
    target_url = target_url or settings.database_url
    if not source_url:
        return {"seeded": False, "reason": "seed database not found"}
    if source_url == target_url:
        return {"seeded": False, "reason": "seed source is the target database"}

    source_engine = create_engine(source_url, future=True)
    target_engine = create_engine(target_url, future=True)
    Base.metadata.create_all(target_engine)
    counts = {"datasets": 0, "models": 0, "alerts": 0}
    try:
        with Session(source_engine) as source, Session(target_engine) as target:
            datasets = target.scalar(select(DatasetRecord.id).limit(1))
            models = target.scalar(select(ModelRecord.id).limit(1))
            alerts = target.scalar(select(AlertRecord.id).limit(1))
            if not datasets and not models:
                counts["datasets"] = _copy_rows(source, target, DatasetRecord)
                counts["models"] = _copy_rows(source, target, ModelRecord)
            if not alerts:
                counts["alerts"] = _copy_rows(source, target, AlertRecord)
            target.commit()
    finally:
        source_engine.dispose()
        target_engine.dispose()
    seeded = any(counts.values())
    return {"seeded": seeded, "source": source_url, "counts": counts}


def main() -> int:
    result = seed_from_sqlite()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
