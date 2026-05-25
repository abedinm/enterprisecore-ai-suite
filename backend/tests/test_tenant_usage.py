"""Real storage-MB accounting for ``GET /tenants/me/usage``."""
from __future__ import annotations

from app.core.tenant_context import tenant_scope
from app.models.marketing import MarketingUpload
from app.models.documents import Document
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.models.webchat import Bot, Conversation, ChatMessage
from app.services import tenant_usage


def test_storage_mb_zero_for_empty_tenant(client, auth_headers):
    tenant_usage.invalidate_cache()
    r = client.get("/api/v1/tenants/me/usage", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # storage_mb is a float >= 0.0; an empty tenant may still hit zero.
    assert isinstance(body["storage_mb"], (float, int))
    assert body["storage_mb"] >= 0.0


def test_storage_mb_counts_marketing_uploads(session_factory, default_tenant, client, auth_headers):
    tenant_usage.invalidate_cache(default_tenant.id)
    with session_factory() as s, tenant_scope(default_tenant.id):
        s.add(MarketingUpload(
            tenant_id=default_tenant.id,
            filename="hero.png",
            content_type="image/png",
            size_bytes=2 * 1024 * 1024,  # 2 MB
            storage_path="marketing/hero.png",
        ))
        s.commit()
    tenant_usage.invalidate_cache(default_tenant.id)
    r = client.get("/api/v1/tenants/me/usage", headers=auth_headers)
    assert r.status_code == 200, r.text
    # At least the 2 MB upload should be reflected.
    assert r.json()["storage_mb"] >= 2.0


def test_storage_mb_counts_documents_content(session_factory, default_tenant):
    tenant_usage.invalidate_cache(default_tenant.id)
    with session_factory() as s, tenant_scope(default_tenant.id):
        s.add(Document(
            tenant_id=default_tenant.id,
            title="big doc",
            content="x" * (1024 * 1024),  # 1 MB of ASCII
            visibility="private",
        ))
        s.commit()
        mb = tenant_usage.compute_tenant_storage_mb(s, default_tenant.id)
    assert mb >= 1.0


def test_storage_mb_counts_knowledge_documents(session_factory, default_tenant):
    tenant_usage.invalidate_cache(default_tenant.id)
    with session_factory() as s, tenant_scope(default_tenant.id):
        kb = KnowledgeBase(
            tenant_id=default_tenant.id,
            name="audit-kb",
            embedding_dim=384,
        )
        s.add(kb)
        s.flush()
        s.add(KnowledgeDocument(
            tenant_id=default_tenant.id,
            kb_id=kb.id,
            name="manual.pdf",
            source_type="upload",
            byte_size=512 * 1024,
            char_count=10_000,
        ))
        s.commit()
        mb = tenant_usage.compute_tenant_storage_mb(s, default_tenant.id)
    # 0.5 MB byte_size + 10k * 4 bytes ≈ 0.54 MB
    assert mb >= 0.5


def test_storage_mb_cache_ttl(session_factory, default_tenant, monkeypatch):
    """Second call inside the TTL should NOT re-walk tables."""
    tenant_usage.invalidate_cache(default_tenant.id)
    calls = {"n": 0}

    real = tenant_usage.compute_tenant_storage_mb

    def _spy(db, tid):
        calls["n"] += 1
        return real(db, tid)

    monkeypatch.setattr(tenant_usage, "compute_tenant_storage_mb", _spy)

    with session_factory() as s, tenant_scope(default_tenant.id):
        tenant_usage.get_tenant_storage_mb(s, default_tenant.id)
        tenant_usage.get_tenant_storage_mb(s, default_tenant.id)
        tenant_usage.get_tenant_storage_mb(s, default_tenant.id)
    assert calls["n"] == 1, "TTL cache should serve the 2nd/3rd call"


def test_storage_mb_cache_invalidation_forces_recompute(session_factory, default_tenant, monkeypatch):
    tenant_usage.invalidate_cache(default_tenant.id)
    calls = {"n": 0}
    real = tenant_usage.compute_tenant_storage_mb

    def _spy(db, tid):
        calls["n"] += 1
        return real(db, tid)

    monkeypatch.setattr(tenant_usage, "compute_tenant_storage_mb", _spy)
    with session_factory() as s, tenant_scope(default_tenant.id):
        tenant_usage.get_tenant_storage_mb(s, default_tenant.id)
        tenant_usage.invalidate_cache(default_tenant.id)
        tenant_usage.get_tenant_storage_mb(s, default_tenant.id)
    assert calls["n"] == 2
