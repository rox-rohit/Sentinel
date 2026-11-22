"""Persistence for digital twins and their ingested samples.

Device tokens are never stored in the clear: only a random salt, a PBKDF2
digest and a short display prefix are persisted, so a database dump cannot be
replayed against the ingest endpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select

from sentinel.store.db import DeviceRecord, DeviceSampleRecord, session_scope

TOKEN_PREFIX_LENGTH = 12
PBKDF2_ITERATIONS = 120_000
MAX_SAMPLES_PER_DEVICE = 600
MODES = ("manual", "auto")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digest(token: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, PBKDF2_ITERATIONS).hex()


def _device_payload(record: DeviceRecord, *, token: str | None = None) -> dict:
    payload = {
        "device_id": record.device_id,
        "name": record.name,
        "asset_id": record.asset_id,
        "mode": record.mode,
        "interval_ms": record.interval_ms,
        "token_prefix": record.token_prefix,
        "notes": record.notes,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "last_seen_at": record.last_seen_at.isoformat() if record.last_seen_at else None,
    }
    if token is not None:
        # Shown once, at creation or rotation; only the digest is stored.
        payload["token"] = token
    return payload


def create_device(*, name: str, asset_id: str | None, mode: str = "manual",
                  interval_ms: int = 1500, notes: str | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}.")
    token = "sntl_" + secrets.token_urlsafe(30)
    salt = secrets.token_hex(16)
    device_id = "dev_" + secrets.token_hex(6)
    with session_scope() as session:
        record = DeviceRecord(
            device_id=device_id,
            name=name.strip()[:120],
            asset_id=(asset_id or None),
            mode=mode,
            interval_ms=int(interval_ms),
            token_prefix=token[:TOKEN_PREFIX_LENGTH],
            token_hash=_digest(token, salt),
            token_salt=salt,
            notes=notes,
        )
        session.add(record)
        session.flush()
        return _device_payload(record, token=token)


def list_devices() -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(select(DeviceRecord).order_by(DeviceRecord.created_at.desc())).all()
        return [_device_payload(row) for row in rows]


def get_device(device_id: str) -> dict | None:
    with session_scope() as session:
        row = session.scalars(
            select(DeviceRecord).where(DeviceRecord.device_id == device_id)
        ).first()
        return _device_payload(row) if row else None


def update_device(device_id: str, **changes) -> dict | None:
    with session_scope() as session:
        row = session.scalars(
            select(DeviceRecord).where(DeviceRecord.device_id == device_id)
        ).first()
        if row is None:
            return None
        if "name" in changes and changes["name"]:
            row.name = str(changes["name"]).strip()[:120]
        if "asset_id" in changes:
            row.asset_id = changes["asset_id"] or None
        if "mode" in changes and changes["mode"]:
            if changes["mode"] not in MODES:
                raise ValueError(f"mode must be one of {', '.join(MODES)}.")
            row.mode = changes["mode"]
        if "interval_ms" in changes and changes["interval_ms"] is not None:
            row.interval_ms = int(changes["interval_ms"])
        if "notes" in changes:
            row.notes = changes["notes"]
        row.updated_at = _utcnow()
        session.flush()
        return _device_payload(row)


def rotate_token(device_id: str) -> dict | None:
    token = "sntl_" + secrets.token_urlsafe(30)
    salt = secrets.token_hex(16)
    with session_scope() as session:
        row = session.scalars(
            select(DeviceRecord).where(DeviceRecord.device_id == device_id)
        ).first()
        if row is None:
            return None
        row.token_prefix = token[:TOKEN_PREFIX_LENGTH]
        row.token_salt = salt
        row.token_hash = _digest(token, salt)
        row.updated_at = _utcnow()
        session.flush()
        return _device_payload(row, token=token)


def verify_token(device_id: str, token: str) -> dict | None:
    """Constant-time check of a device bearer token."""
    if not token:
        return None
    with session_scope() as session:
        row = session.scalars(
            select(DeviceRecord).where(DeviceRecord.device_id == device_id)
        ).first()
        if row is None:
            return None
        candidate = _digest(token, row.token_salt)
        if not hmac.compare_digest(candidate, row.token_hash):
            return None
        return _device_payload(row)


def delete_device(device_id: str) -> bool:
    with session_scope() as session:
        row = session.scalars(
            select(DeviceRecord).where(DeviceRecord.device_id == device_id)
        ).first()
        if row is None:
            return False
        session.delete(row)
        session.query(DeviceSampleRecord).filter(
            DeviceSampleRecord.device_id == device_id
        ).delete()
        return True


def append_sample(
    device_id: str,
    *,
    sensors: dict[str, float],
    assessment: dict,
    cycle: int | None = None,
    source: str = "manual",
    recorded_at: datetime | None = None,
) -> dict:
    with session_scope() as session:
        device = session.scalars(
            select(DeviceRecord).where(DeviceRecord.device_id == device_id)
        ).first()
        if device is None:
            raise LookupError(f"Unknown device {device_id}")
        last_seq = session.scalar(
            select(func.max(DeviceSampleRecord.seq)).where(DeviceSampleRecord.device_id == device_id)
        ) or 0
        record = DeviceSampleRecord(
            device_id=device_id,
            seq=int(last_seq) + 1,
            cycle=cycle,
            source=source,
            health=assessment.get("health_score"),
            anomaly=assessment.get("anomaly_score"),
            severity=assessment.get("severity"),
            coverage=(assessment.get("coverage") or {}).get("coverage"),
            sensors_json=json.dumps(sensors, separators=(",", ":")),
            at=recorded_at or _utcnow(),
        )
        session.add(record)
        device.last_seen_at = record.at
        device.updated_at = _utcnow()
        session.flush()
        payload = {
            "seq": record.seq,
            "at": record.at.isoformat(),
            "cycle": record.cycle,
            "source": record.source,
            "health": record.health,
            "anomaly": record.anomaly,
            "severity": record.severity,
            "coverage": record.coverage,
            "sensors": sensors,
        }
        if record.seq % 100 == 0:
            _prune(session, device_id)
        return payload


def _prune(session, device_id: str) -> None:
    cutoff = session.scalar(
        select(func.max(DeviceSampleRecord.seq)).where(DeviceSampleRecord.device_id == device_id)
    )
    if not cutoff or cutoff <= MAX_SAMPLES_PER_DEVICE:
        return
    session.query(DeviceSampleRecord).filter(
        DeviceSampleRecord.device_id == device_id,
        DeviceSampleRecord.seq <= int(cutoff) - MAX_SAMPLES_PER_DEVICE,
    ).delete()


def list_samples(device_id: str, limit: int = 120) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(DeviceSampleRecord)
            .where(DeviceSampleRecord.device_id == device_id)
            .order_by(DeviceSampleRecord.seq.desc())
            .limit(limit)
        ).all()
        return [
            {
                "seq": row.seq,
                "at": row.at.isoformat() if row.at else None,
                "cycle": row.cycle,
                "source": row.source,
                "health": row.health,
                "anomaly": row.anomaly,
                "severity": row.severity,
                "coverage": row.coverage,
                "sensors": json.loads(row.sensors_json or "{}"),
            }
            for row in reversed(rows)
        ]


def sample_count(device_id: str) -> int:
    with session_scope() as session:
        return int(session.scalar(
            select(func.count(DeviceSampleRecord.id)).where(
                DeviceSampleRecord.device_id == device_id
            )
        ) or 0)
