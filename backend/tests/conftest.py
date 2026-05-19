"""Pytest fixtures: isolated SQLite DB, TestClient, authenticated admin headers."""
from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Environment must be set BEFORE the app imports settings.
# We point the suite at a throw-away SQLite file and a deterministic secret.
# ---------------------------------------------------------------------------
_TMP_DIR = Path(tempfile.mkdtemp(prefix="ec_tests_"))
_TEST_DB = _TMP_DIR / "test.db"

os.environ["DB_BACKEND"] = "sqlite"
os.environ["SQLITE_PATH"] = str(_TEST_DB)
os.environ["SECRET_KEY"] = "test-secret-" + secrets.token_urlsafe(32)
os.environ["APP_ENV"] = "development"
os.environ["APP_DEBUG"] = "false"
# Disable real AI calls in tests
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["AI_DEFAULT_PROVIDER"] = "ollama"

# Import AFTER env is patched.
from app.api.deps import get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    """Create a fresh SQLite engine, build the schema, seed the default admin."""
    url = f"sqlite:///{_TEST_DB.as_posix()}"
    eng = create_engine(url, connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_connection, _):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()
    # Clean up the temp DB file
    try:
        _TEST_DB.unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True, scope="session")
def _seed_admin(session_factory):
    """Make sure the default admin exists exactly once."""
    with session_factory() as db:
        from sqlalchemy import select
        existing = db.scalar(select(User).where(User.email == "admin@local"))
        if not existing:
            db.add(User(
                email="admin@local",
                full_name="Test Admin",
                password_hash=hash_password("ChangeMe123!"),
                role=UserRole.admin,
                is_active=True,
            ))
            db.commit()


@pytest.fixture(scope="session")
def client(session_factory):
    """TestClient with the get_db dependency redirected at the test session factory."""

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    # ALSO override the duplicate get_db in app.db.session if anything imports it directly
    try:
        from app.db.session import get_db as session_get_db
        app.dependency_overrides[session_get_db] = _override_get_db
    except Exception:
        pass

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def admin_token(client) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": "admin@local", "password": "ChangeMe123!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def db(session_factory):
    """A short-lived DB session for tests that need direct ORM access."""
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Wipe both rate-limiter buckets between tests so one test's burst doesn't
    poison the next. The rate-limit-specific test bursts after this reset, so it
    still exercises the real limiter."""
    try:
        from app.core.rate_limit import limiter, reset_dependency_limiter
        limiter.reset()
        reset_dependency_limiter()
    except Exception:
        pass
    yield
