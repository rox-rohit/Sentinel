"""Operational metadata store: dataset versions, model registry, alerts.

SQLAlchemy with a SQLite default; point `SENTINEL_DATABASE_URL` at PostgreSQL for
a shared deployment. No database-specific SQL is used.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from sentinel.config import settings


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DatasetRecord(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(32))
    rows: Mapped[int] = mapped_column(Integer)
    columns: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(255))
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    schema_json: Mapped[str] = mapped_column(Text, default="{}")
    source_url: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ModelRecord(Base):
    __tablename__ = "models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    task: Mapped[str] = mapped_column(String(48))
    dataset: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(32))
    algorithm: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="candidate")  # candidate | active | archived
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    artifact_path: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AlertRecord(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    cycle: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Session:
    init_db()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_datasets() -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(select(DatasetRecord).order_by(DatasetRecord.created_at.desc())).all()
        return [
            {
                "id": r.id, "name": r.name, "display_name": r.display_name, "version": r.version,
                "rows": r.rows, "columns": r.columns, "path": r.path,
                "quality": json.loads(r.quality_json), "schema": json.loads(r.schema_json),
                "source_url": r.source_url, "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


def list_models() -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(select(ModelRecord).order_by(ModelRecord.created_at.desc())).all()
        return [
            {
                "id": r.id, "name": r.name, "task": r.task, "dataset": r.dataset,
                "version": r.version, "algorithm": r.algorithm, "status": r.status,
                "metrics": json.loads(r.metrics_json), "params": json.loads(r.params_json),
                "artifact_path": r.artifact_path, "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


def list_alerts(limit: int = 50) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(AlertRecord).order_by(AlertRecord.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": r.id, "asset_id": r.asset_id, "severity": r.severity, "kind": r.kind,
                "message": r.message, "cycle": r.cycle, "score": r.score,
                "acknowledged": r.acknowledged, "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
