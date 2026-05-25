"""Tenant deletion endpoint — DELETE /api/v1/tenants/me."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import settings as app_settings
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.documents import Document
from app.models.marketing import MarketingUpload
from app.models.tenant import Tenant
from app.models.user import User


def _signup_tenant(client, slug: str) -> dict:
    payload = {
        "name": f"Tenant {slug}",
        "slug": slug,
        "admin_email": f"admin@{slug}.test",
        "admin_password": "DelPass123!",
        "admin_full_name": f"Admin {slug}",
    }
    r = client.post("/api/v1/tenants/signup", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    return {
        "tenant_id": body["tenant"]["id"],
        "slug": body["tenant"]["slug"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


def test_delete_wrong_confirmation_returns_400(client):
    info = _signup_tenant(client, "deltest-wrongconf")
    r = client.request(
        "DELETE",
        "/api/v1/tenants/me",
        json={"confirmation": "WRONG"},
        headers=info["headers"],
    )
    assert r.status_code == 400, r.text
    # The tenant must still exist.
    me = client.get("/api/v1/tenants/me", headers=info["headers"])
    assert me.status_code == 200


def test_delete_non_admin_returns_403(client):
    info = _signup_tenant(client, "deltest-nonadmin")
    # Create an employee inside the new tenant via invite + accept.
    inv = client.post(
        "/api/v1/tenants/me/users/invite",
        json={"email": f"emp@deltest-nonadmin.test", "role": "Employee"},
        headers=info["headers"],
    ).json()
    token = inv["token"]
    accepted = client.post(
        "/api/v1/tenants/accept-invite",
        json={"token": token, "password": "EmpPass99!", "full_name": "Employee"},
    ).json()
    emp_headers = {"Authorization": f"Bearer {accepted['access_token']}"}

    r = client.request(
        "DELETE",
        "/api/v1/tenants/me",
        json={"confirmation": "DELETE-MY-TENANT"},
        headers=emp_headers,
    )
    assert r.status_code == 403, r.text


def test_successful_deletion_returns_204_and_writes_receipt(client, session_factory):
    info = _signup_tenant(client, "deltest-success")
    tenant_id = info["tenant_id"]

    # Seed a few rows so the receipt has non-zero counts.
    with session_factory() as s, tenant_scope(tenant_id):
        s.add(MarketingUpload(
            tenant_id=tenant_id,
            filename="dummy.png",
            content_type="image/png",
            size_bytes=100,
            storage_path="dummy.png",
        ))
        s.add(Document(
            tenant_id=tenant_id,
            title="bye doc",
            content="goodbye",
            visibility="private",
        ))
        s.commit()

    r = client.request(
        "DELETE",
        "/api/v1/tenants/me",
        json={"confirmation": "DELETE-MY-TENANT", "reason": "compliance test"},
        headers=info["headers"],
    )
    assert r.status_code == 204, r.text

    # Tenant row gone.
    with session_factory() as s, bypass_tenant_filter():
        assert s.get(Tenant, tenant_id) is None
        # No users left.
        users = s.scalar(select(func.count(User.id)).where(User.tenant_id == tenant_id))
        assert (users or 0) == 0
        # No marketing uploads.
        uploads = s.scalar(
            select(func.count(MarketingUpload.id)).where(MarketingUpload.tenant_id == tenant_id)
        )
        assert (uploads or 0) == 0
        # No documents.
        docs = s.scalar(
            select(func.count(Document.id)).where(Document.tenant_id == tenant_id)
        )
        assert (docs or 0) == 0

    # Receipt file exists.
    receipt_dir = Path(app_settings.storage_dir) / "deletion-receipts"
    matches = list(receipt_dir.glob(f"{tenant_id}-*.json"))
    assert matches, f"No receipt file under {receipt_dir}"
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    assert data["tenant_id"] == tenant_id
    assert data["reason"] == "compliance test"
    assert data["deleted_record_counts"].get("users", 0) >= 1
    assert data["deleted_record_counts"].get("marketing_uploads", 0) >= 1
    assert data["deleted_record_counts"].get("documents", 0) >= 1


def test_cross_tenant_isolation_during_delete(client, session_factory):
    """Deleting tenant A must NOT touch tenant B's rows."""
    a = _signup_tenant(client, "deltest-iso-a")
    b = _signup_tenant(client, "deltest-iso-b")

    with session_factory() as s, tenant_scope(b["tenant_id"]):
        s.add(Document(
            tenant_id=b["tenant_id"],
            title="b doc",
            content="b survives",
            visibility="private",
        ))
        s.commit()

    r = client.request(
        "DELETE",
        "/api/v1/tenants/me",
        json={"confirmation": "DELETE-MY-TENANT"},
        headers=a["headers"],
    )
    assert r.status_code == 204

    # B must still be intact + B's document still readable.
    with session_factory() as s, bypass_tenant_filter():
        b_tenant = s.get(Tenant, b["tenant_id"])
        assert b_tenant is not None
        b_docs = s.scalar(
            select(func.count(Document.id)).where(Document.tenant_id == b["tenant_id"])
        )
        assert (b_docs or 0) >= 1
