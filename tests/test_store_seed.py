"""Hosted-store bootstrap: copy build metadata into an empty Postgres-compatible store."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from sentinel.config import ARTIFACTS
from sentinel.store.db import AlertRecord, DatasetRecord, ModelRecord
from sentinel.store.seed import seed_from_sqlite

SOURCE = ARTIFACTS / "sentinel.db"


@pytest.mark.skipif(not SOURCE.exists(), reason="run `python -m sentinel.pipelines.build` first")
def test_seed_copies_registry_alerts_and_is_idempotent(tmp_path):
    target_url = f"sqlite:///{(tmp_path / 'hosted.db').as_posix()}"
    result = seed_from_sqlite(SOURCE, target_url)
    assert result["seeded"] is True
    assert result["counts"]["datasets"] > 0
    assert result["counts"]["models"] > 0
    assert result["counts"]["alerts"] > 0

    engine = create_engine(target_url, future=True)
    with Session(engine) as session:
        assert session.scalar(select(DatasetRecord.id).limit(1)) is not None
        assert session.scalar(select(ModelRecord.id).limit(1)) is not None
        assert session.scalar(select(AlertRecord.id).limit(1)) is not None
    engine.dispose()

    again = seed_from_sqlite(SOURCE, target_url)
    assert again["seeded"] is False
    assert again["counts"] == {"datasets": 0, "models": 0, "alerts": 0}
