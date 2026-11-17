"""Operational metadata store: dataset versions, model registry, alerts.

SQLAlchemy with a SQLite default; point `SENTINEL_DATABASE_URL` at PostgreSQL for
a shared deployment. No database-specific SQL is used.

Alerts carry a deterministic fingerprint (asset + kind + cycle) so a rebuild
updates the alert without discarding its acknowledgement or resolution state.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, Integer, String, Text, create_engine,
                        inspect, select, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from sentinel.config import settings

ALERT_STATUSES = ("open", "acknowledged", "resolved")


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
    fingerprint: Mapped[str] = mapped_column(String(40), index=True, default="")
    asset_id: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    severity: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    cycle: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    # Nullable lifecycle fields are annotated without a union: SQLAlchemy 2's
    # string-annotation resolution fails on `datetime | None` under Python 3.15.
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str] = mapped_column(String(80), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str] = mapped_column(String(80), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class MaintenanceScenarioRecord(Base):
    __tablename__ = "maintenance_scenarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    budget: Mapped[float] = mapped_column(Float)
    spent: Mapped[float] = mapped_column(Float, default=0.0)
    expected_avoided_loss: Mapped[float] = mapped_column(Float, default=0.0)
    expected_downtime_hours: Mapped[float] = mapped_column(Float, default=0.0)
    assets_serviced: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def alert_fingerprint(asset_id: str, kind: str, cycle: int) -> str:
    """Stable identity across rebuilds: the same asset/kind/cycle is the same alert."""
    digest = hashlib.sha1(f"{asset_id}|{kind}|{int(cycle)}".encode("utf-8")).hexdigest()
    return digest[:32]


_ALERT_COLUMN_MIGRATIONS = {
    "fingerprint": "VARCHAR(40)",
    "label": "VARCHAR(64) NOT NULL DEFAULT ''",
    "status": "VARCHAR(16) NOT NULL DEFAULT 'open'",
    "acknowledged_at": "TIMESTAMP",
    "acknowledged_by": "VARCHAR(80)",
    "resolved_at": "TIMESTAMP",
    "resolved_by": "VARCHAR(80)",
    "note": "TEXT",
    "updated_at": "TIMESTAMP",
}


def _migrate_alerts() -> None:
    """Add lifecycle columns to a database created by an earlier build."""
    inspector = inspect(engine)
    if "alerts" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("alerts")}
    with engine.begin() as connection:
        for name, ddl in _ALERT_COLUMN_MIGRATIONS.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE alerts ADD COLUMN {name} {ddl}"))
        if "fingerprint" not in existing:
            for row in connection.execute(text("SELECT id, asset_id, kind, cycle FROM alerts")).all():
                connection.execute(
                    text("UPDATE alerts SET fingerprint = :fingerprint WHERE id = :id"),
                    {
                        "fingerprint": alert_fingerprint(row.asset_id, row.kind, row.cycle),
                        "id": row.id,
                    },
                )
        if "status" not in existing:
            connection.execute(text(
                "UPDATE alerts SET status = CASE WHEN acknowledged THEN 'acknowledged' "
                "ELSE 'open' END"
            ))


def init_db() -> None:
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _migrate_alerts()


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


def _alert_payload(record: AlertRecord) -> dict:
    return {
        "id": record.id,
        "fingerprint": record.fingerprint,
        "asset_id": record.asset_id,
        "label": record.label or record.asset_id,
        "sensors": [],
        "severity": record.severity,
        "kind": record.kind,
        "message": record.message,
        "cycle": record.cycle,
        "score": record.score,
        "status": record.status,
        "acknowledged": record.acknowledged,
        "acknowledged_at": record.acknowledged_at.isoformat() if record.acknowledged_at else None,
        "acknowledged_by": record.acknowledged_by,
        "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
        "resolved_by": record.resolved_by,
        "note": record.note,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def list_alerts(limit: int = 50, status: str | None = None,
                asset_id: str | None = None) -> list[dict]:
    with session_scope() as session:
        statement = select(AlertRecord).order_by(AlertRecord.created_at.desc()).limit(limit)
        if status:
            statement = statement.where(AlertRecord.status == status)
        if asset_id:
            statement = statement.where(AlertRecord.asset_id == asset_id)
        rows = session.scalars(statement).all()
        return [_alert_payload(row) for row in rows]


def alert_counts() -> dict:
    counts = {status: 0 for status in ALERT_STATUSES}
    with session_scope() as session:
        for row in session.scalars(select(AlertRecord)).all():
            counts[row.status] = counts.get(row.status, 0) + 1
    counts["total"] = sum(counts.values())
    return counts


def get_alert(alert_id: int) -> dict | None:
    with session_scope() as session:
        record = session.get(AlertRecord, alert_id)
        return _alert_payload(record) if record else None


def acknowledge_alert(alert_id: int, *, actor: str, note: str | None = None) -> dict | None:
    with session_scope() as session:
        record = session.get(AlertRecord, alert_id)
        if record is None:
            return None
        if record.status == "resolved":
            raise ValueError("A resolved alert cannot be acknowledged.")
        record.status = "acknowledged"
        record.acknowledged = True
        record.acknowledged_at = record.acknowledged_at or _utcnow()
        record.acknowledged_by = actor
        if note:
            record.note = note
        record.updated_at = _utcnow()
        session.flush()
        return _alert_payload(record)


def resolve_alert(alert_id: int, *, actor: str, note: str | None = None) -> dict | None:
    with session_scope() as session:
        record = session.get(AlertRecord, alert_id)
        if record is None:
            return None
        if record.status == "resolved":
            raise ValueError("Alert is already resolved.")
        record.status = "resolved"
        record.acknowledged = True
        record.acknowledged_at = record.acknowledged_at or _utcnow()
        record.resolved_at = _utcnow()
        record.resolved_by = actor
        if note:
            record.note = note
        record.updated_at = _utcnow()
        session.flush()
        return _alert_payload(record)


def _scenario_payload(record: MaintenanceScenarioRecord, *, include_plan: bool = False) -> dict:
    from sentinel.decision.scenarios import summarize_plan

    plan = json.loads(record.payload_json)
    payload = summarize_plan(
        plan, scenario_id=record.id, name=record.name, note=record.note,
        created_at=record.created_at.isoformat(),
    )
    if include_plan:
        payload["plan"] = plan
    return payload


def save_scenario(name: str, plan: dict, note: str | None = None) -> dict:
    """Persist a computed optimisation plan under a human-readable name."""
    with session_scope() as session:
        record = MaintenanceScenarioRecord(
            name=name.strip(),
            note=note,
            budget=float(plan.get("budget", 0.0)),
            spent=float(plan.get("spent", 0.0)),
            expected_avoided_loss=float(plan.get("expected_avoided_loss", 0.0)),
            expected_downtime_hours=float(plan.get("expected_downtime_hours", 0.0)),
            assets_serviced=len(plan.get("selected", [])),
            payload_json=json.dumps(plan, default=str),
        )
        session.add(record)
        session.flush()
        return _scenario_payload(record)


def list_scenarios(limit: int = 50) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(MaintenanceScenarioRecord)
            .order_by(MaintenanceScenarioRecord.created_at.desc())
            .limit(limit)
        ).all()
        return [_scenario_payload(row) for row in rows]


def get_scenario(scenario_id: int) -> dict | None:
    with session_scope() as session:
        record = session.get(MaintenanceScenarioRecord, scenario_id)
        return _scenario_payload(record, include_plan=True) if record else None


def delete_scenario(scenario_id: int) -> bool:
    with session_scope() as session:
        record = session.get(MaintenanceScenarioRecord, scenario_id)
        if record is None:
            return False
        session.delete(record)
        return True


def sync_alerts(alerts: list[dict], *, prune: bool = True) -> dict:
    """Insert new alerts, refresh existing ones, keep their lifecycle state.

    Alerts that are no longer produced by the pipeline are deleted only while
    still open; acknowledged/resolved alerts remain as an audit trail.
    """
    current = {alert_fingerprint(a["asset_id"], a["kind"], a["cycle"]) for a in alerts}
    created = updated = removed = 0
    with session_scope() as session:
        rows = {row.fingerprint: row for row in session.scalars(select(AlertRecord)).all()}
        for alert in alerts:
            fingerprint = alert_fingerprint(alert["asset_id"], alert["kind"], alert["cycle"])
            row = rows.get(fingerprint)
            if row is None:
                session.add(AlertRecord(
                    fingerprint=fingerprint,
                    asset_id=alert["asset_id"],
                    label=alert.get("label", alert["asset_id"]),
                    severity=alert["severity"],
                    kind=alert["kind"],
                    message=alert["message"],
                    cycle=int(alert["cycle"]),
                    score=float(alert["score"]),
                    status="open",
                    acknowledged=False,
                ))
                created += 1
            else:
                row.label = alert.get("label", alert["asset_id"])
                row.severity = alert["severity"]
                row.message = alert["message"]
                row.score = float(alert["score"])
                updated += 1
        for fingerprint, row in rows.items():
            if prune and fingerprint not in current and row.status == "open":
                session.delete(row)
                removed += 1
    return {"created": created, "updated": updated, "removed": removed}
