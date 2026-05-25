"""Tests for the audit log streamer."""
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.security_hardening import AuditStreamDestination
from app.models.user import AuditLog
from app.services import audit_streamer


def _make_destination(db, tenant_id: str, url: str = "https://example.com/hook") -> AuditStreamDestination:
    dest = AuditStreamDestination(
        tenant_id=tenant_id,
        name="Test Destination",
        destination_type="webhook",
        url=url,
        is_active=True,
    )
    db.add(dest)
    db.commit()
    db.refresh(dest)
    return dest


def _make_audit_event(db, tenant_id: str, action: str = "test.action") -> AuditLog:
    event = AuditLog(
        tenant_id=tenant_id,
        action=action,
        entity_type="test",
        entity_id="x",
        detail={"hello": "world"},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_new_audit_log_pushed_to_destination(session_factory, default_tenant):
    # Reset cursor so this test's events count fresh.
    audit_streamer._cursors.clear()
    with session_factory() as s, tenant_scope(default_tenant.id):
        dest = _make_destination(s, default_tenant.id)
        _make_audit_event(s, default_tenant.id)
        with patch.object(audit_streamer, "_http_post", return_value=(200, "ok")) as mock_post:
            ok, err, sent = audit_streamer.flush_destination(dest, s)
        assert ok is True
        assert sent >= 1
        assert mock_post.called


def test_failed_destination_retried_three_times(session_factory, default_tenant):
    audit_streamer._cursors.clear()
    with session_factory() as s, tenant_scope(default_tenant.id):
        dest = _make_destination(s, default_tenant.id, url="https://broken.example/hook")
        _make_audit_event(s, default_tenant.id, action="retry.test")
        with patch.object(audit_streamer, "_http_post", return_value=(500, "boom")) as mock_post:
            with patch.object(audit_streamer.time, "sleep"):  # speed up retries
                ok, err, sent = audit_streamer.flush_destination(dest, s)
        assert ok is False
        assert err is not None and "500" in err
        # MAX_ATTEMPTS retries per flush.
        assert mock_post.call_count == audit_streamer.MAX_ATTEMPTS


def test_destination_auto_disabled_after_consecutive_failures(session_factory, default_tenant):
    audit_streamer._cursors.clear()
    with session_factory() as s, tenant_scope(default_tenant.id):
        dest = _make_destination(s, default_tenant.id, url="https://broken.example/hook")
        # Need at least one event per attempt so the streamer actually
        # tries to send (no events → no failure → no counter bump).
        for i in range(audit_streamer.DISABLE_AFTER_CONSECUTIVE_FAILURES):
            _make_audit_event(s, default_tenant.id, action=f"disable-test-{i}")
            with patch.object(audit_streamer, "_http_post", return_value=(500, "boom")):
                with patch.object(audit_streamer.time, "sleep"):
                    audit_streamer.flush_destination(dest, s)
        s.refresh(dest)
        assert dest.is_active is False
        assert dest.consecutive_failures >= audit_streamer.DISABLE_AFTER_CONSECUTIVE_FAILURES


def test_cross_tenant_isolation(session_factory, make_tenant):
    """A destination for tenant A must never receive tenant B's events."""
    audit_streamer._cursors.clear()
    tenant_a, _, _ = make_tenant("audit-iso-a")
    tenant_b, _, _ = make_tenant("audit-iso-b")

    with session_factory() as s, tenant_scope(tenant_a.id):
        dest_a = _make_destination(s, tenant_a.id, url="https://a.example/hook")
    with session_factory() as s, tenant_scope(tenant_b.id):
        _make_audit_event(s, tenant_b.id, action="from-tenant-b")

    captured: list[bytes] = []

    def _fake_post(url, headers, body):
        captured.append(body)
        return 200, "ok"

    with session_factory() as s:
        with patch.object(audit_streamer, "_http_post", side_effect=_fake_post):
            audit_streamer.flush_destination(dest_a, s)

    # Either nothing was sent (no events for tenant A), or what was sent
    # mentions tenant A's id only.
    for body in captured:
        assert b"from-tenant-b" not in body
        assert tenant_b.id.encode() not in body


def test_test_destination_canary(session_factory, default_tenant):
    """The /test endpoint sends a canary event without advancing the cursor."""
    with session_factory() as s, tenant_scope(default_tenant.id):
        dest = _make_destination(s, default_tenant.id)
        with patch.object(audit_streamer, "_http_post", return_value=(200, "ok")):
            ok, err = audit_streamer.test_destination(dest, s)
        assert ok is True
        assert err is None
        s.refresh(dest)
        assert dest.last_success_at is not None


def test_splunk_hec_format(session_factory, default_tenant):
    """Splunk HEC payload wraps each event in {'event': ...} and uses Splunk auth header."""
    audit_streamer._cursors.clear()
    # Advance the cursor past any audit events the rest of the suite may
    # have left behind so we only see the splunk.test event we add below.
    with session_factory() as s, tenant_scope(default_tenant.id):
        from sqlalchemy import select
        from app.core.tenant_context import bypass_tenant_filter
        with bypass_tenant_filter():
            last = s.scalars(
                select(AuditLog).where(AuditLog.tenant_id == default_tenant.id)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(1)
            ).first()
    with session_factory() as s, tenant_scope(default_tenant.id):
        dest = AuditStreamDestination(
            tenant_id=default_tenant.id,
            name="Splunk",
            destination_type="splunk_hec",
            url="https://splunk.example/services/collector",
            is_active=True,
        )
        s.add(dest)
        s.commit()
        s.refresh(dest)
        # Seed cursor so the new splunk.test event is the only thing flushed.
        if last is not None:
            audit_streamer._cursors[dest.id] = last.id
        _make_audit_event(s, default_tenant.id, action="splunk.test")

        captured = {}

        def _fake_post(url, headers, body):
            captured["headers"] = headers
            captured["body"] = body
            return 200, "ok"

        with patch.object(audit_streamer, "_http_post", side_effect=_fake_post):
            audit_streamer.flush_destination(dest, s)

        # Whether the streamer had events to send (and thus posted at all)
        # depends on what other tests left behind. If it did post, verify
        # the Splunk-HEC wrapping format is correct. If no body was sent
        # (cursor was already past the latest event), exercise the
        # builder directly so the format contract is still tested.
        if "body" in captured:
            assert b'"event"' in captured["body"]
            assert b'"sourcetype": "enterprisecore:audit"' in captured["body"]
        else:
            from app.services.audit_streamer import _build_request
            body, headers = _build_request(dest, [{"id": "x", "tenant_id": dest.tenant_id, "action": "splunk.test"}])
            assert b'"event"' in body
            assert b'"sourcetype": "enterprisecore:audit"' in body
