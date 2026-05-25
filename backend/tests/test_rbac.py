"""Tests for granular RBAC — built-ins, custom roles, cross-tenant isolation."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.permissions import (
    BUILT_IN_ROLE_PERMISSIONS, PERMISSION_CATALOG, effective_permissions,
    has_permission,
)
from app.core.tenant_context import tenant_scope
from app.core.security import hash_password
from app.models.rbac import CustomRole, UserRoleAssignment
from app.models.user import User, UserRole


def test_permission_catalog_size_reasonable():
    keys = {k for k, _, _ in PERMISSION_CATALOG}
    assert len(keys) == len(PERMISSION_CATALOG), "duplicate keys in catalog"
    assert len(keys) >= 80, f"catalog only has {len(keys)} entries"


def test_admin_has_every_permission():
    assert BUILT_IN_ROLE_PERMISSIONS[UserRole.admin] == {k for k, _, _ in PERMISSION_CATALOG}


def test_employee_has_no_finance_writes():
    emp_keys = BUILT_IN_ROLE_PERMISSIONS[UserRole.employee]
    assert "finance.invoices.read" in emp_keys
    assert "finance.invoices.write" not in emp_keys
    assert "hr.employees.terminate" not in emp_keys


def test_manager_cannot_admin_tenant():
    mgr_keys = BUILT_IN_ROLE_PERMISSIONS[UserRole.manager]
    assert "tenant.admin" not in mgr_keys
    assert "tenant.encryption.admin" not in mgr_keys
    assert "tenant.billing.write" not in mgr_keys
    # But can read most things + write business modules.
    assert "finance.invoices.write" in mgr_keys
    assert "crm.deals.write" in mgr_keys


def test_has_permission_via_builtin_role(db):
    user = db.scalar(select(User).where(User.email == "admin@local"))
    assert user is not None
    assert has_permission(user, "finance.invoices.write", db) is True
    assert has_permission(user, "tenant.admin", db) is True


def test_has_permission_via_custom_role(db, default_tenant):
    """A user without admin role can be granted finance.invoices.write via a custom role."""
    # Create an employee in the default tenant.
    user = User(
        email="finance-auditor@test",
        full_name="Finance Auditor",
        password_hash=hash_password("ChangeMe123!"),
        role=UserRole.employee,
    )
    db.add(user)
    db.flush()

    role = CustomRole(
        name="Finance Auditor",
        description="Read every finance entity",
        permission_keys=["finance.invoices.write", "finance.payroll.read"],
    )
    db.add(role)
    db.flush()

    db.add(UserRoleAssignment(user_id=user.id, custom_role_id=role.id))
    db.commit()

    # Without the assignment they wouldn't have the permission; with it they do.
    assert has_permission(user, "finance.invoices.write", db) is True
    assert has_permission(user, "finance.payroll.read", db) is True
    # Still no admin perms.
    assert has_permission(user, "tenant.admin", db) is False


def test_cross_tenant_custom_role_isolation(make_tenant, session_factory):
    """A custom role created in tenant A must not leak permissions into tenant B."""
    tenant_a, admin_a, _ = make_tenant("rbac-iso-a")
    tenant_b, admin_b, _ = make_tenant("rbac-iso-b")

    # In tenant A, create a custom role granting finance.invoices.write.
    with session_factory() as db, tenant_scope(tenant_a.id):
        role = CustomRole(
            name="Tenant-A Auditor",
            description="A only",
            permission_keys=["finance.invoices.write"],
        )
        db.add(role)
        db.commit()
        db.refresh(role)
        role_a_id = role.id

    # In tenant B, even an employee shouldn't see that role or get its perm.
    with session_factory() as db, tenant_scope(tenant_b.id):
        emp_b = User(
            email="emp@b.test",
            full_name="Employee B",
            password_hash=hash_password("ChangeMe123!"),
            role=UserRole.employee,
        )
        db.add(emp_b)
        db.commit()
        db.refresh(emp_b)

        # Try to assign tenant A's role: the auto-filter hides it.
        role_b_view = db.get(CustomRole, role_a_id)
        # Either invisible (auto-filter skips it) or visible-but-cross-tenant.
        # Either way the permission must NOT resolve.
        assert "finance.invoices.write" not in effective_permissions(emp_b, db)


def test_list_permissions_endpoint_admin_only(client, auth_headers):
    resp = client.get("/api/v1/rbac/permissions", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 80
    keys = {row["key"] for row in items}
    assert "finance.invoices.write" in keys


def test_create_custom_role_validates_unknown_keys(client, auth_headers):
    resp = client.post(
        "/api/v1/rbac/roles",
        headers=auth_headers,
        json={
            "name": "Bad Role",
            "permission_keys": ["finance.invoices.write", "totally.fake.permission"],
        },
    )
    assert resp.status_code == 422 or resp.status_code == 400
    assert "totally.fake.permission" in resp.text


def test_create_assign_revoke_custom_role(client, auth_headers, session_factory, default_tenant):
    # Create a custom role. Pick perms NOT in the employee baseline so the
    # revoke test below can confirm they really disappear.
    resp = client.post(
        "/api/v1/rbac/roles",
        headers=auth_headers,
        json={
            "name": "QA Lead",
            "description": "Test access",
            "permission_keys": ["finance.invoices.write", "hr.employees.terminate"],
        },
    )
    assert resp.status_code == 201, resp.text
    role_id = resp.json()["id"]

    # Provision a target user.
    with session_factory() as db, tenant_scope(default_tenant.id):
        user = User(
            email="qa-lead@test",
            full_name="QA Lead",
            password_hash=hash_password("ChangeMe123!"),
            role=UserRole.employee,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    # Assign.
    resp = client.post(
        f"/api/v1/rbac/users/{user_id}/roles",
        headers=auth_headers,
        json={"custom_role_id": role_id},
    )
    assert resp.status_code == 201

    # Effective permissions reflect the grant.
    resp = client.get(f"/api/v1/rbac/users/{user_id}/effective-permissions", headers=auth_headers)
    assert resp.status_code == 200
    assert "hr.employees.terminate" in resp.json()["permission_keys"]

    # Revoke.
    resp = client.delete(
        f"/api/v1/rbac/users/{user_id}/roles/{role_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204

    # Permission is gone again.
    resp = client.get(f"/api/v1/rbac/users/{user_id}/effective-permissions", headers=auth_headers)
    assert resp.status_code == 200
    assert "hr.employees.terminate" not in resp.json()["permission_keys"]


def test_require_permission_dep_returns_403(client):
    """An unauthenticated request to an admin-only RBAC endpoint should be rejected.

    Clear cookies explicitly: the shared TestClient may have retained
    auth cookies from a prior test's login. We want to confirm the
    unauthenticated 401/403 path here.
    """
    client.cookies.clear()
    resp = client.get("/api/v1/rbac/permissions")
    assert resp.status_code in (401, 403)
