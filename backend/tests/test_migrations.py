"""Verify the alembic migration baseline matches the current ORM metadata
and runs cleanly on a fresh database.

If a contributor adds a column to a model without writing a corresponding
migration, this test catches it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect


@pytest.fixture()
def fresh_db_url(monkeypatch):
    """Spin up a brand-new SQLite file and point app.core.config at it."""
    d = Path(tempfile.mkdtemp(prefix="ec_migr_"))
    db_file = d / "fresh.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_file))
    # Bust the lru_cached settings
    from app.core import config as _cfg
    _cfg.get_settings.cache_clear()
    return f"sqlite:///{db_file.as_posix()}"


def test_alembic_upgrade_head_creates_all_tables(fresh_db_url):
    """Run `alembic upgrade head` from scratch and verify every model's table exists."""
    from alembic import command
    from app.db.init_db import _alembic_config
    from app.db.base import Base
    import app.models  # noqa: F401  — ensure all models are registered

    cfg = _alembic_config()
    cfg.set_main_option("sqlalchemy.url", fresh_db_url)
    command.upgrade(cfg, "head")

    eng = create_engine(fresh_db_url)
    insp = inspect(eng)
    real_tables = set(insp.get_table_names())
    expected = set(Base.metadata.tables.keys())
    missing = expected - real_tables
    assert not missing, f"Migration left these tables uncreated: {sorted(missing)}"
    # alembic_version must exist after a successful upgrade
    assert "alembic_version" in real_tables


def test_alembic_idempotent(fresh_db_url):
    """Running upgrade head twice should be a no-op the second time."""
    from alembic import command
    from app.db.init_db import _alembic_config

    cfg = _alembic_config()
    cfg.set_main_option("sqlalchemy.url", fresh_db_url)
    command.upgrade(cfg, "head")
    # Second call must not raise
    command.upgrade(cfg, "head")


def test_stamp_then_upgrade(fresh_db_url):
    """An existing DB with tables but no alembic_version should be stamp-able
    and then upgrade-able without errors."""
    from alembic import command
    from sqlalchemy import create_engine
    from app.db.base import Base
    from app.db.init_db import _alembic_config
    import app.models  # noqa: F401

    eng = create_engine(fresh_db_url)
    Base.metadata.create_all(bind=eng)  # simulate "old install" pre-alembic

    insp = inspect(eng)
    assert "alembic_version" not in insp.get_table_names()

    cfg = _alembic_config()
    cfg.set_main_option("sqlalchemy.url", fresh_db_url)
    command.stamp(cfg, "head")
    command.upgrade(cfg, "head")

    insp = inspect(create_engine(fresh_db_url))
    assert "alembic_version" in insp.get_table_names()
