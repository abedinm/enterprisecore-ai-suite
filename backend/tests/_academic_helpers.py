"""Shared helpers for the academic test suite.

Test-only — not imported by app code.
"""
from __future__ import annotations

from sqlalchemy import select


def set_edu_plan(monkeypatch):
    """Force the active plan to EDU so academic endpoints respond at all."""
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=True, state="active", reason="stub",
        customer="acme", plan="edu",
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)


def make_user(client, email: str, role_value: str, *, password: str = "ChangeMe123!"):
    """Create a user with the given role (string value, e.g. ``"Student"``)
    via the test DB session and log them in. Returns the auth headers dict.

    We reuse the same DB file the TestClient is wired to via the conftest
    session factory — going through ``/api/v1/users`` would require admin
    auth and an Employee→Teacher promotion, which is fussier than just
    seeding the row directly.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.security import hash_password
    from app.models.user import User, UserRole
    from tests.conftest import _TEST_DB

    eng = create_engine(
        f"sqlite:///{_TEST_DB.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SessionMaker = sessionmaker(
        bind=eng, autoflush=False, autocommit=False,
        expire_on_commit=False, future=True,
    )
    with SessionMaker() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if not existing:
            db.add(User(
                email=email, full_name=email.split("@")[0].title(),
                password_hash=hash_password(password),
                role=UserRole(role_value),
                is_active=True,
            ))
            db.commit()
        elif existing.role.value != role_value:
            existing.role = UserRole(role_value)
            db.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def get_user_id(email: str) -> str:
    """Look up a user's id by email — used when test code needs to reference
    a freshly-made user as a teacher / student in another payload."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.user import User
    from tests.conftest import _TEST_DB

    eng = create_engine(
        f"sqlite:///{_TEST_DB.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SessionMaker = sessionmaker(
        bind=eng, autoflush=False, autocommit=False,
        expire_on_commit=False, future=True,
    )
    with SessionMaker() as db:
        u = db.scalar(select(User).where(User.email == email))
        assert u is not None, f"user {email} not found"
        return u.id


def make_semester(client, auth_headers, name: str = "Spring 2026", **overrides):
    """Create a semester via the API. Caller can override start/end dates."""
    from datetime import date
    payload = {
        "name": name,
        "start_date": date(2026, 1, 15).isoformat(),
        "end_date": date(2026, 5, 30).isoformat(),
        "is_current": True,
    }
    payload.update(overrides)
    r = client.post(
        "/api/v1/academic/semesters", headers=auth_headers, json=payload,
    )
    assert r.status_code == 201, r.text
    return r.json()


def make_room(client, auth_headers, name: str = "Room 101", **overrides):
    payload = {"name": name, "capacity": 30}
    payload.update(overrides)
    r = client.post(
        "/api/v1/academic/rooms", headers=auth_headers, json=payload,
    )
    assert r.status_code == 201, r.text
    return r.json()


def make_class(
    client, auth_headers, *, teacher_id: str, semester_id: str,
    name: str = "Intro to CS", course_code: str = "CS101",
):
    r = client.post(
        "/api/v1/academic/classes/",
        headers=auth_headers,
        json={
            "name": name, "course_code": course_code,
            "teacher_id": teacher_id, "semester_id": semester_id,
            "credit_hours": 3,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()
