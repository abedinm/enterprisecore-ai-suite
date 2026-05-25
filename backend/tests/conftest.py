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
from app.core.tenant_context import bypass_tenant_filter, tenant_scope  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

# Slug of the test tenant — every test row gets attached here unless a test
# explicitly creates its own tenant for isolation testing.
TEST_TENANT_SLUG = "default"


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
    """Make sure the default tenant + admin user exist exactly once.

    Bypass the auto-filter while we provision the tenant (no tenant
    context is set this early). The admin user is created inside the new
    tenant's scope so the auto-set hook populates tenant_id.
    """
    with session_factory() as db:
        from sqlalchemy import select
        with bypass_tenant_filter():
            tenant = db.scalar(select(Tenant).where(Tenant.slug == TEST_TENANT_SLUG))
            if not tenant:
                tenant = Tenant(
                    name="Default Tenant",
                    slug=TEST_TENANT_SLUG,
                    plan="evaluation",
                    status="active",
                    settings={},
                    primary_contact_email="admin@local",
                    timezone="UTC",
                    currency="USD",
                )
                db.add(tenant)
                db.commit()
                db.refresh(tenant)

        with tenant_scope(tenant.id):
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
    """A short-lived DB session for tests that need direct ORM access.

    Auto-scoped to the default test tenant — most tests poke ORM rows for
    that tenant and don't care about multi-tenancy. Tests that *do* care
    (cross-tenant attack, isolation) use the ``tenant_a``/``tenant_b``
    fixtures below to set their own scope.
    """
    from sqlalchemy import select
    s = session_factory()
    try:
        with bypass_tenant_filter():
            tenant = s.scalar(select(Tenant).where(Tenant.slug == TEST_TENANT_SLUG))
        with tenant_scope(tenant.id if tenant else None):
            yield s
    finally:
        s.close()


@pytest.fixture()
def default_tenant(session_factory) -> Tenant:
    """The default test tenant. Cached at session scope but exposed as a
    per-test fixture for convenience."""
    from sqlalchemy import select
    with session_factory() as s, bypass_tenant_filter():
        tenant = s.scalar(select(Tenant).where(Tenant.slug == TEST_TENANT_SLUG))
        assert tenant is not None
        return tenant


@pytest.fixture()
def make_tenant(session_factory):
    """Factory that creates a brand-new tenant + its admin user.

    Returned tuple is ``(tenant, admin_user, bearer_token)`` — the token
    is ready to use as ``Authorization: Bearer ...`` in TestClient calls.
    """
    from sqlalchemy import select
    from app.core.security import create_access_token

    created: list[str] = []

    def _make(slug: str, *, plan: str = "evaluation"):
        with session_factory() as s, bypass_tenant_filter():
            existing = s.scalar(select(Tenant).where(Tenant.slug == slug))
            if existing:
                tenant = existing
            else:
                tenant = Tenant(
                    name=f"Tenant {slug}",
                    slug=slug,
                    plan=plan,
                    status="active",
                    settings={},
                    primary_contact_email=f"admin@{slug}.test",
                    timezone="UTC",
                    currency="USD",
                )
                s.add(tenant)
                s.commit()
                s.refresh(tenant)
            created.append(tenant.id)

        with session_factory() as s, tenant_scope(tenant.id):
            admin_email = f"admin@{slug}.test"
            existing = s.scalar(select(User).where(User.email == admin_email))
            if existing:
                user = existing
            else:
                user = User(
                    email=admin_email,
                    full_name=f"Admin {slug}",
                    password_hash=hash_password("ChangeMe123!"),
                    role=UserRole.admin,
                    is_active=True,
                )
                s.add(user)
                s.commit()
                s.refresh(user)
            token = create_access_token(user.id, user.role.value)
            return tenant, user, token

    return _make


@pytest.fixture(autouse=True)
def _reset_audit_streamer():
    """Wipe the audit_streamer cursor map between tests so order-of-execution
    cannot leave one test's last-sent cursor in place when another test runs
    expecting a fresh slate. Without this, the splunk_hec format test was
    flaky depending on which test ran before it."""
    try:
        from app.services import audit_streamer as _audit_streamer
        _audit_streamer.reset_for_tests()
    except Exception:
        pass
    yield


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


@pytest.fixture(autouse=True)
def _set_default_tenant_scope(session_factory):
    """Auto-scope every test's foreground operations to the default tenant.

    Many tests open a session via ``session_factory()`` and insert rows
    directly — without this fixture they'd run with no tenant context, the
    auto-set hook wouldn't fire, and the NOT NULL tenant_id constraint would
    reject every insert. Tests that explicitly want a different scope (the
    isolation suite) use ``tenant_scope(...)`` inside their own with-block,
    which nests correctly.
    """
    from sqlalchemy import select
    with session_factory() as s, bypass_tenant_filter():
        tenant = s.scalar(select(Tenant).where(Tenant.slug == TEST_TENANT_SLUG))
    token = None
    if tenant:
        from app.core.tenant_context import tenant_id_ctx
        token = tenant_id_ctx.set(tenant.id)
    try:
        yield
    finally:
        if token is not None:
            from app.core.tenant_context import tenant_id_ctx
            tenant_id_ctx.reset(token)
