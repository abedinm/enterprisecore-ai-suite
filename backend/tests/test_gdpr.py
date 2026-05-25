"""Tests for GDPR data-export + erasure endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.webhooks import GdprErasureReceipt, GdprExportJob


def _make_user(db, *, email: str, role: UserRole = UserRole.employee) -> User:
    u = User(
        email=email,
        full_name=f"User {email}",
        password_hash=hash_password("ChangeMe123!"),
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_data_categories_documented(client, auth_headers):
    r = client.get("/api/v1/gdpr/data-categories", headers=auth_headers)
    assert r.status_code == 200
    cats = r.json()
    names = {c["name"] for c in cats}
    assert "Account" in names
    assert "AI usage" in names


def test_export_creates_job_and_file(client, auth_headers, db):
    r = client.post("/api/v1/gdpr/export", json={}, headers=auth_headers)
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "ready"
    assert job["download_url"]
    assert job["record_count"] >= 1

    # Poll endpoint returns the same job.
    r2 = client.get(f"/api/v1/gdpr/export/{job['id']}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "ready"

    # Bundle file is on disk.
    job_obj = db.get(GdprExportJob, job["id"])
    assert job_obj is not None
    bundle_path = Path("storage") / job_obj.download_path.replace("\\", "/")
    assert bundle_path.exists()
    bundle = json.loads(bundle_path.read_text("utf-8"))
    assert bundle["user_id"] == job_obj.user_id
    assert "records_by_table" in bundle
    # Secrets must not leak.
    assert bundle["profile"]["password_hash"] == "<redacted>"


def test_export_download_requires_token(client, auth_headers, db):
    r = client.post("/api/v1/gdpr/export", json={}, headers=auth_headers)
    assert r.status_code == 202
    job_id = r.json()["id"]

    # Without token: 422 (missing required query param).
    r1 = client.get(f"/api/v1/gdpr/export/{job_id}/download", headers=auth_headers)
    assert r1.status_code == 422

    # With wrong token: 403.
    r2 = client.get(
        f"/api/v1/gdpr/export/{job_id}/download?token=bad", headers=auth_headers,
    )
    assert r2.status_code == 403

    # With correct token: 200.
    job = db.get(GdprExportJob, job_id)
    r3 = client.get(
        f"/api/v1/gdpr/export/{job_id}/download?token={job.download_token}",
        headers=auth_headers,
    )
    assert r3.status_code == 200


def test_erasure_anonymizes_user(client, auth_headers, db):
    target = _make_user(db, email="erase-me@example.com")
    r = client.post(
        "/api/v1/gdpr/erasure-request",
        json={"user_id": target.id, "reason": "User requested"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text

    db.expire_all()
    refreshed = db.get(User, target.id)
    assert refreshed.email != "erase-me@example.com"
    assert refreshed.email.startswith("erased-")
    assert refreshed.full_name == "<deleted>"
    assert refreshed.is_active is False

    receipt = db.scalar(
        select(GdprErasureReceipt).where(GdprErasureReceipt.user_id == target.id)
    )
    assert receipt is not None
    assert receipt.reason == "User requested"


def test_erasure_requires_admin(client, db, make_tenant):
    # Create a non-admin user in a fresh tenant + try to call the endpoint.
    tenant, _admin, _token = make_tenant("emp-tenant")
    from app.core.security import create_access_token
    from app.core.tenant_context import tenant_scope

    with tenant_scope(tenant.id):
        emp = User(
            email="emp@emp-tenant.test",
            full_name="Emp",
            password_hash=hash_password("ChangeMe123!"),
            role=UserRole.employee,
            is_active=True,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
        emp_token = create_access_token(emp.id, emp.role.value)

    headers = {"Authorization": f"Bearer {emp_token}"}
    r = client.post(
        "/api/v1/gdpr/erasure-request",
        json={"user_id": emp.id, "reason": "self"},
        headers=headers,
    )
    assert r.status_code == 403


def test_erasure_receipts_admin_only(client, auth_headers):
    r = client.get("/api/v1/gdpr/erasure-receipts", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_cross_tenant_export_blocked(client, db, make_tenant, auth_headers):
    """An admin in tenant A cannot export a user in tenant B."""

    # Build a user in tenant-b
    tenant_b, b_admin, _ = make_tenant("gdpr-tenant-b")

    # The default tenant's admin tries to export the tenant-b admin.
    r = client.post(
        "/api/v1/gdpr/export",
        json={"user_id": b_admin.id},
        headers=auth_headers,
    )
    # The tenant auto-filter hides the user, so the endpoint sees them as missing.
    assert r.status_code == 404


def test_admin_cannot_self_erase(client, auth_headers, db):
    # The admin@local seeded by conftest should hit the self-erase guard.
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    r = client.post(
        "/api/v1/gdpr/erasure-request",
        json={"user_id": admin.id, "reason": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 400
