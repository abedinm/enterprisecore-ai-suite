"""Marketing Industry Templates — service helpers, endpoints, JSON validation.

Covers the Phase 3 templates pack: the three shipped JSON files (restaurant,
consultancy, professional_services), the service helpers that load and apply
them, and the three new endpoints (list, get, apply). Plan gating is already
covered by ``test_marketing_api.test_marketing_gated_off_when_feature_removed``
so we don't re-test it here — instead we make sure the new admin-only apply
endpoint also rejects non-privileged callers.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.marketing import (
    MarketingFAQ, MarketingNavItem, MarketingPost, MarketingProject,
    MarketingSection, MarketingService, MarketingSettings, MarketingSocialLink,
    MarketingTeamMember, MarketingTestimonial,
)
from app.services import marketing as svc


API = "/api/v1/marketing"

# Templates shipped in this build. If any are renamed, update here too — the
# tests are intentionally explicit so a silent rename doesn't slip through.
EXPECTED_TEMPLATE_IDS = {"restaurant", "consultancy", "professional_services"}

# Lists every "list-shaped" entity the templates can populate. Used by the
# wipe / apply tests to assert all rows are gone or all are present.
_LIST_MODELS = (
    MarketingSection, MarketingProject, MarketingPost, MarketingService,
    MarketingTestimonial, MarketingFAQ, MarketingTeamMember,
    MarketingSocialLink, MarketingNavItem,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _wipe_all_marketing(db) -> None:
    """Remove every marketing list-row + reset the settings singleton so each
    test starts from a known baseline. Settings is reset by deleting + letting
    ``get_settings`` recreate it on the next service call."""
    for model in _LIST_MODELS:
        db.query(model).delete()
    db.query(MarketingSettings).delete()
    db.commit()


def _count(db, model) -> int:
    return db.query(model).count()


# ---------------------------------------------------------------------------
# Service: list_templates
# ---------------------------------------------------------------------------
def test_list_templates_returns_three_entries_with_metadata():
    rows = svc.list_templates()
    ids = {r["id"] for r in rows}
    assert ids == EXPECTED_TEMPLATE_IDS, f"expected {EXPECTED_TEMPLATE_IDS}, got {ids}"
    # Each entry has the four metadata fields the gallery card needs.
    for r in rows:
        assert set(r.keys()) >= {"id", "name", "description", "preview_image"}
        assert isinstance(r["name"], str) and r["name"]
        assert isinstance(r["description"], str) and r["description"]


# ---------------------------------------------------------------------------
# Service: get_template
# ---------------------------------------------------------------------------
def test_get_template_returns_full_payload_for_restaurant():
    tpl = svc.get_template("restaurant")
    assert tpl is not None
    assert tpl["id"] == "restaurant"
    # Settings block populated with the warm restaurant palette.
    assert tpl["settings"]["primary_color"] == "#B7472A"
    assert tpl["settings"]["name"] == "Corner Table"
    # Sections, services, etc. are non-empty arrays.
    assert len(tpl["sections"]) >= 1
    assert len(tpl["services"]) >= 1
    assert len(tpl["testimonials"]) >= 1
    assert any(s["type"] == "hero" for s in tpl["sections"])


def test_get_template_returns_none_for_unknown_id():
    assert svc.get_template("nope") is None
    assert svc.get_template("") is None


def test_get_template_rejects_path_traversal():
    """Path-traversal segments must be refused before any filesystem lookup."""
    assert svc.get_template("../etc/passwd") is None
    assert svc.get_template("../../app/main") is None
    assert svc.get_template("subdir/restaurant") is None


# ---------------------------------------------------------------------------
# Service: apply_template — wipe + insert
# ---------------------------------------------------------------------------
def test_apply_template_wipes_and_inserts_template_rows(db):
    _wipe_all_marketing(db)
    # Seed some "existing" content that should be wiped.
    db.add(MarketingService(title="Stale service", order=0))
    db.add(MarketingProject(title="Stale project", slug="stale-project", order=0))
    db.commit()
    assert _count(db, MarketingService) == 1
    assert _count(db, MarketingProject) == 1

    state = svc.apply_template(db, "restaurant", wipe_existing=True)

    # Old rows gone, template's rows in their place.
    assert not any(s.title == "Stale service" for s in db.scalars(select(MarketingService)).all())
    assert not any(p.title == "Stale project" for p in db.scalars(select(MarketingProject)).all())
    assert _count(db, MarketingService) == 4  # restaurant.json ships 4 services
    assert _count(db, MarketingProject) == 4
    # Returned state matches what was just written.
    assert state.settings.name == "Corner Table"
    assert len(state.services) == 4


def test_apply_template_updates_settings_in_place_singleton_not_duplicated(db):
    _wipe_all_marketing(db)
    svc.apply_template(db, "consultancy", wipe_existing=True)
    settings_rows = db.scalars(select(MarketingSettings)).all()
    assert len(settings_rows) == 1
    assert settings_rows[0].key == "default"
    assert settings_rows[0].name == "Northwell Partners"

    # Apply a second template — still exactly one row, updated in place.
    svc.apply_template(db, "professional_services", wipe_existing=True)
    settings_rows = db.scalars(select(MarketingSettings)).all()
    assert len(settings_rows) == 1
    assert settings_rows[0].name == "Meridian Engineering"
    assert settings_rows[0].primary_color == "#1A5C35"


def test_apply_template_without_wipe_appends_to_existing_rows(db):
    _wipe_all_marketing(db)
    # Seed one of each entity that the template will also try to add.
    db.add(MarketingService(title="Existing service", order=99))
    db.add(MarketingTestimonial(quote="Existing quote", order=99))
    db.commit()
    before_services = _count(db, MarketingService)
    before_testimonials = _count(db, MarketingTestimonial)

    svc.apply_template(db, "consultancy", wipe_existing=False)

    # The "existing" rows are still there, plus the template's additions.
    assert _count(db, MarketingService) == before_services + 4  # consultancy ships 4
    assert _count(db, MarketingTestimonial) == before_testimonials + 3
    titles = {s.title for s in db.scalars(select(MarketingService)).all()}
    assert "Existing service" in titles
    assert "Strategy" in titles  # one of the consultancy services


def test_apply_template_unknown_id_raises_and_does_not_mutate(db):
    from app.core.exceptions import ValidationFailed
    _wipe_all_marketing(db)
    db.add(MarketingService(title="Untouched", order=0))
    db.commit()
    try:
        svc.apply_template(db, "does-not-exist", wipe_existing=True)
    except ValidationFailed as exc:
        assert "not found" in str(exc).lower()
    else:
        raise AssertionError("Expected ValidationFailed for unknown template")
    # The existing row is still there — failure happened before any wipe.
    assert _count(db, MarketingService) == 1


# ---------------------------------------------------------------------------
# Endpoints: list + get
# ---------------------------------------------------------------------------
def test_endpoint_list_templates_returns_three(client, auth_headers):
    r = client.get(f"{API}/templates", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    ids = {row["id"] for row in body}
    assert ids == EXPECTED_TEMPLATE_IDS


def test_endpoint_get_template_returns_full_payload(client, auth_headers):
    r = client.get(f"{API}/templates/professional_services", headers=auth_headers)
    assert r.status_code == 200, r.text
    tpl = r.json()
    assert tpl["id"] == "professional_services"
    # Six-stage ladder is the differentiator for this template.
    assert len(tpl["services"]) == 6
    assert tpl["services"][0]["title"].startswith("Stage 1")


def test_endpoint_get_template_returns_404_for_unknown_id(client, auth_headers):
    r = client.get(f"{API}/templates/nope", headers=auth_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint: POST .../use — admin happy path + non-admin rejection
# ---------------------------------------------------------------------------
def test_endpoint_use_template_replaces_state_for_admin(client, auth_headers, db):
    _wipe_all_marketing(db)
    r = client.post(
        f"{API}/templates/restaurant/use",
        headers=auth_headers,
        json={"wipe_existing": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["settings"]["name"] == "Corner Table"
    # Sample fields from the template are present in the returned state.
    assert any(s["type"] == "hero" for s in body["sections"])
    assert len(body["services"]) == 4
    assert any("brunch" in svc["title"].lower() for svc in body["services"])


def test_endpoint_use_template_writes_notification_for_actor(client, auth_headers, db):
    from app.models.user import Notification, User
    _wipe_all_marketing(db)
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    before = db.query(Notification).filter_by(user_id=admin.id).count()

    r = client.post(
        f"{API}/templates/consultancy/use",
        headers=auth_headers,
        json={"wipe_existing": True},
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    after_rows = db.scalars(
        select(Notification).where(Notification.user_id == admin.id)
    ).all()
    assert len(after_rows) == before + 1
    latest = sorted(after_rows, key=lambda n: n.created_at)[-1]
    assert "consultancy" in latest.title.lower() or "boutique" in latest.title.lower()


def test_endpoint_use_template_rejects_non_admin(client):
    """Employee role must be blocked at the require_roles dependency."""
    # Register + login as a fresh employee. Using a unique email keeps this
    # test independent of any other test in the suite that might have used
    # the same address.
    email = "marketing-tpl-emp@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Marketing TPL Emp", "password": "AbcDefGh12"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "AbcDefGh12"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    r = client.post(
        f"{API}/templates/restaurant/use",
        headers=headers,
        json={"wipe_existing": True},
    )
    assert r.status_code == 403, r.text
    assert r.json().get("code") == "permission_denied"


def test_endpoint_use_template_404_for_unknown_template(client, auth_headers):
    r = client.post(
        f"{API}/templates/nope/use",
        headers=auth_headers,
        json={"wipe_existing": True},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# JSON validation — every shipped template parses + has required structure
# ---------------------------------------------------------------------------
_REQUIRED_TOP_KEYS = {
    "id", "name", "description", "preview_image", "settings", "navigation",
    "sections", "projects", "posts", "services", "testimonials", "faqs",
    "team", "social_links",
}

_REQUIRED_SETTINGS_KEYS = {
    "name", "tagline", "primary_color", "accent_color", "heading_font",
    "body_font", "theme_mode",
}


def test_every_template_has_required_top_level_keys():
    for tid in EXPECTED_TEMPLATE_IDS:
        tpl = svc.get_template(tid)
        assert tpl is not None, tid
        missing = _REQUIRED_TOP_KEYS - set(tpl.keys())
        assert not missing, f"{tid} missing top-level keys: {missing}"
        assert tpl["id"] == tid


def test_every_template_settings_block_has_required_keys():
    for tid in EXPECTED_TEMPLATE_IDS:
        tpl = svc.get_template(tid)
        s = tpl["settings"]
        missing = _REQUIRED_SETTINGS_KEYS - set(s.keys())
        assert not missing, f"{tid}.settings missing: {missing}"
        # Color values are hex strings — cheap sanity check.
        assert s["primary_color"].startswith("#")
        assert s["accent_color"].startswith("#")


def test_every_template_entity_lists_are_lists():
    list_keys = ("navigation", "sections", "projects", "posts", "services",
                 "testimonials", "faqs", "team", "social_links")
    for tid in EXPECTED_TEMPLATE_IDS:
        tpl = svc.get_template(tid)
        for k in list_keys:
            assert isinstance(tpl[k], list), f"{tid}.{k} is not a list"


def test_every_template_post_has_slug_and_status():
    for tid in EXPECTED_TEMPLATE_IDS:
        tpl = svc.get_template(tid)
        for post in tpl["posts"]:
            assert post.get("slug"), f"{tid}: post missing slug — {post.get('title')}"
            assert post.get("status") in {"draft", "published"}, \
                f"{tid}: post has invalid status — {post.get('status')}"


def test_every_template_section_has_required_fields():
    for tid in EXPECTED_TEMPLATE_IDS:
        tpl = svc.get_template(tid)
        for sec in tpl["sections"]:
            assert sec.get("type") in {"hero", "services", "projects",
                                       "testimonials", "about", "cta"}, \
                f"{tid}: section has invalid type — {sec.get('type')}"
            assert "enabled" in sec
            assert "order" in sec
            assert "payload" in sec and isinstance(sec["payload"], dict)


def test_every_template_project_tags_are_string_lists():
    for tid in EXPECTED_TEMPLATE_IDS:
        tpl = svc.get_template(tid)
        for proj in tpl["projects"]:
            assert isinstance(proj.get("tags", []), list)
            for tag in proj.get("tags", []):
                assert isinstance(tag, str), f"{tid}: non-string tag in project {proj.get('title')}"
