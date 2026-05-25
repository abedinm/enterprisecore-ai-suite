"""End-to-end multi-tenant isolation tests.

These verify the auto-filter actually rewrites every SELECT to scope by
the current tenant, and that the ``before_insert`` hook auto-populates
tenant_id on new rows. Each test creates two tenants (A and B), exercises
a cross-tenant attack vector, and asserts the boundary holds.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.ai import AiConversation
from app.models.communication import WikiPage
from app.models.construction.projects import ConstructionProject
from app.models.crm import Contact
from app.models.finance import Customer
from app.models.hr import Employee
from app.models.inventory import Product
from app.models.knowledge import KnowledgeBase
from app.models.marketing import MarketingPost
from app.models.projects import Project
from app.models.tenant import Tenant
from app.models.user import User
from app.models.webchat import Bot


# ---------------------------------------------------------------------------
# Per-test fixture: two fresh tenants, each with their own admin token.
# ---------------------------------------------------------------------------
@pytest.fixture()
def two_tenants(make_tenant):
    """Create tenant A + tenant B, return their (tenant, user, token) tuples."""
    a = make_tenant("iso-a")
    b = make_tenant("iso-b")
    return a, b


# ---------------------------------------------------------------------------
# Direct ORM isolation — per module.
# ---------------------------------------------------------------------------
def test_customers_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants

    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Customer(name="Acme A1"))
        s.add(Customer(name="Acme A2"))
        s.commit()

    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(Customer(name="Globex B1"))
        s.commit()

    with session_factory() as s, tenant_scope(tenant_a.id):
        names = sorted(c.name for c in s.scalars(select(Customer)))
        assert names == ["Acme A1", "Acme A2"]

    with session_factory() as s, tenant_scope(tenant_b.id):
        names = sorted(c.name for c in s.scalars(select(Customer)))
        assert names == ["Globex B1"]


def test_employees_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants

    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Employee(employee_code="EMP-A1", full_name="Alice"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(Employee(employee_code="EMP-A1", full_name="Bob"))
        s.commit()

    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = s.scalars(select(Employee)).all()
        assert len(rows) == 1 and rows[0].full_name == "Alice"
    with session_factory() as s, tenant_scope(tenant_b.id):
        rows = s.scalars(select(Employee)).all()
        assert len(rows) == 1 and rows[0].full_name == "Bob"


def test_contacts_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Contact(name="A Lead", email="a@a.test"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(Contact(name="B Lead", email="b@b.test"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_a.id):
        assert all(c.email == "a@a.test" for c in s.scalars(select(Contact)))


def test_projects_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Project(name="A Project"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        rows = s.scalars(select(Project)).all()
        assert len(rows) == 0


def test_products_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Product(sku="WIDGET-1", name="A Widget"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(Product(sku="WIDGET-1", name="B Widget"))  # same SKU, different tenant — ok
        s.commit()
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = s.scalars(select(Product)).all()
        assert len(rows) == 1 and rows[0].name == "A Widget"


def test_marketing_posts_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(MarketingPost(title="A Post", slug="welcome"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(MarketingPost(title="B Post", slug="welcome"))  # same slug, ok
        s.commit()
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = list(s.scalars(select(MarketingPost)))
        assert len(rows) == 1 and rows[0].title == "A Post"


def test_construction_projects_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(ConstructionProject(name="Bridge A", project_type="infrastructure"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        rows = s.scalars(select(ConstructionProject)).all()
        assert len(rows) == 0


def test_knowledge_bases_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(KnowledgeBase(name="A KB"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        assert s.scalars(select(KnowledgeBase)).all() == []


def test_webchat_bots_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, user_a, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Bot(owner_id=user_a.id, name="A Bot"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        assert s.scalars(select(Bot)).all() == []


def test_wiki_pages_isolated_between_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(WikiPage(slug="onboarding", title="A onboarding"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(WikiPage(slug="onboarding", title="B onboarding"))  # same slug, ok
        s.commit()
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = list(s.scalars(select(WikiPage)))
        assert len(rows) == 1 and rows[0].title == "A onboarding"


# ---------------------------------------------------------------------------
# Bypass — sysadmin sees across tenants.
# ---------------------------------------------------------------------------
def test_bypass_filter_sees_all_tenants(session_factory, two_tenants):
    (tenant_a, _, _), (tenant_b, _, _) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Customer(name="A Customer"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(Customer(name="B Customer"))
        s.commit()
    with session_factory() as s, bypass_tenant_filter():
        names = sorted(c.name for c in s.scalars(select(Customer)))
        # Includes both, plus any pre-existing customers from other tests.
        assert "A Customer" in names and "B Customer" in names


# ---------------------------------------------------------------------------
# Auto-set hook fires on insert.
# ---------------------------------------------------------------------------
def test_before_insert_auto_sets_tenant_id(session_factory, two_tenants):
    (tenant_a, _, _), _ = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        customer = Customer(name="Auto-Tagged")
        # NOTE: tenant_id intentionally not set — the hook should fill it in.
        s.add(customer)
        s.commit()
        s.refresh(customer)
        assert customer.tenant_id == tenant_a.id


# ---------------------------------------------------------------------------
# HTTP-layer cross-tenant attacks.
# ---------------------------------------------------------------------------
def test_cross_tenant_user_lookup_returns_404(client, two_tenants):
    """User in tenant A asks for tenant B's user id — must look like the
    record doesn't exist, not 403 (which would leak existence)."""
    (tenant_a, user_a, token_a), (tenant_b, user_b, _) = two_tenants
    r = client.get(
        f"/api/v1/users/{user_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 404


def test_cross_tenant_patch_returns_404(client, two_tenants, session_factory):
    """Customer create in B, then user from A tries to PATCH by id → 404."""
    (tenant_a, _, token_a), (tenant_b, _, token_b) = two_tenants
    with session_factory() as s, tenant_scope(tenant_b.id):
        c = Customer(name="B-customer")
        s.add(c)
        s.commit()
        s.refresh(c)
        b_customer_id = c.id

    r = client.patch(
        f"/api/v1/finance/customers/{b_customer_id}",
        json={"name": "Hijacked"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 404


def test_cross_tenant_list_only_shows_own(client, two_tenants, session_factory):
    (tenant_a, _, token_a), (tenant_b, _, token_b) = two_tenants
    with session_factory() as s, tenant_scope(tenant_a.id):
        s.add(Customer(name="A-only-customer"))
        s.commit()
    with session_factory() as s, tenant_scope(tenant_b.id):
        s.add(Customer(name="B-only-customer"))
        s.commit()

    r = client.get(
        "/api/v1/finance/customers",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 200
    names = {c["name"] for c in r.json()}
    assert "A-only-customer" in names
    assert "B-only-customer" not in names


# ---------------------------------------------------------------------------
# Cascade delete — dropping the tenant removes their data.
# ---------------------------------------------------------------------------
def test_cascade_delete_removes_tenant_data(session_factory, make_tenant):
    """Create a brand-new tenant + a customer row, then DELETE the tenant
    and verify the customer row was cascade-removed."""
    from sqlalchemy import text
    tenant, _, _ = make_tenant("cascade-test")
    with session_factory() as s, tenant_scope(tenant.id):
        s.add(Customer(name="Doomed Customer"))
        s.commit()
        # Sanity: row exists.
        assert s.scalars(select(Customer)).all()

    # Drop the tenant — every FK-CASCADE should remove dependent rows.
    with session_factory() as s, bypass_tenant_filter():
        s.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant.id})
        s.commit()

    with session_factory() as s, bypass_tenant_filter():
        remaining = s.execute(
            text("SELECT COUNT(*) FROM customers WHERE tenant_id = :tid"),
            {"tid": tenant.id},
        ).scalar()
        assert remaining == 0
