"""SiteForge JSON export → EnterpriseCore Marketing import.

Covers: happy path, malformed JSON, non-admin role gate, idempotent
``wipe_existing=true`` re-runs, and field translation (camelCase → snake_case).
"""
from __future__ import annotations

import io
import json

from sqlalchemy import select

from app.models.marketing import (
    MarketingFAQ, MarketingNavItem, MarketingPost, MarketingProject,
    MarketingSection, MarketingService, MarketingSettings, MarketingSocialLink,
    MarketingTeamMember, MarketingTestimonial,
)
from app.services import marketing as svc

API = "/api/v1/marketing"

_LIST_MODELS = (
    MarketingSection, MarketingProject, MarketingPost, MarketingService,
    MarketingTestimonial, MarketingFAQ, MarketingTeamMember,
    MarketingSocialLink, MarketingNavItem,
)


def _wipe_all_marketing(db) -> None:
    for model in _LIST_MODELS:
        db.query(model).delete()
    db.query(MarketingSettings).delete()
    db.commit()


def _minimal_siteforge_export() -> dict:
    """A minimal SiteForge-shaped export with at least one row per major
    entity so tests can verify the field translation."""
    return {
        "siteSettings": {
            "name": "North & Pine",
            "tagline": "Studio for thoughtful businesses",
            "description": "A small studio.",
            "logoText": "North & Pine",
            "logoDot": True,
            "baseUrl": "https://northandpine.studio",
            "seoTitle": "North & Pine — Studio",
            "seoDescription": "Brand and web design.",
        },
        "themeSettings": {
            "mode": "light",
            "primaryColor": "#1f4fd1",
            "accentColor": "#0f172a",
            "headingFont": "Fraunces",
            "bodyFont": "Inter",
            "buttonStyle": "rounded",
            "density": "comfortable",
            "radius": 10,
        },
        "navigation": [
            {"id": "nav_home", "label": "Home", "route": "home", "enabled": True},
            {"id": "nav_work", "label": "Work", "route": "portfolio", "enabled": True},
        ],
        "sections": [
            {
                "id": "sec_hero",
                "type": "hero",
                "enabled": True,
                "eyebrow": "Studio · est. 2019",
                "title": "Design that respects the work.",
                "body": "We build brand systems.",
                "stats": [{"value": "120+", "label": "Projects"}],
            },
        ],
        "projects": [
            {
                "id": "p_1",
                "title": "Field & Garden rebrand",
                "client": "Field & Garden Co.",
                "category": "Identity",
                "summary": "A warm identity.",
                "body": "Long-form case study.",
                "year": "2025",
                "tags": ["identity", "print"],
                "featured": True,
                "url": "https://example.com/fg",
            },
        ],
        "posts": [
            {
                "id": "b_1",
                "title": "Why smallest projects are favorites",
                "slug": "why-smallest",
                "excerpt": "Constraints help.",
                "body": "Long body.",
                "author": "Eve Halden",
                "category": "Studio notes",
                "tags": ["craft"],
                "publishDate": "2026-04-22",
                "status": "published",
                "seoTitle": "Smallest projects",
                "seoDescription": "On constraints.",
            },
        ],
        "services": [
            {
                "id": "s_1",
                "icon": "sparkle",
                "title": "Brand Identity",
                "summary": "Marks and type.",
                "details": "Six-week engagement.",
                "price": "from $9,800",
                "featured": True,
            },
        ],
        "testimonials": [
            {"id": "t_1", "quote": "They asked hard questions.", "author": "Mira Field", "role": "Owner"},
        ],
        "faqs": [
            {"id": "f_1", "q": "How long?", "a": "Six weeks."},
        ],
        "team": [
            {"id": "tm_1", "name": "Eve Halden", "role": "Founder"},
        ],
        "contactInfo": {
            "email": "studio@example.com",
            "phone": "+1 902 555 0142",
            "address": "Halifax NS",
            "hours": "Mon-Thu 9-5",
        },
        "socialLinks": [
            {"id": "sl_1", "platform": "twitter", "label": "@northandpine", "url": "https://twitter.com/"},
        ],
        # SiteForge-only fields that the importer must silently drop:
        "activity": [{"id": "a_1", "kind": "create", "label": "Project created"}],
        "launchChecklist": [{"id": "lc_1", "label": "Site name set", "auto": "siteName"}],
        "meta": {"version": 1, "exported_at": "2026-05-21"},
    }


def _upload(client, headers, payload: dict | str | bytes):
    """POST /import-siteforge as multipart file upload."""
    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = payload
    files = {"file": ("siteforge-export.json", io.BytesIO(raw), "application/json")}
    return client.post(f"{API}/import-siteforge", headers=headers, files=files)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_import_siteforge_happy_path(client, auth_headers, db):
    _wipe_all_marketing(db)
    r = _upload(client, auth_headers, _minimal_siteforge_export())
    assert r.status_code == 200, r.text
    body = r.json()

    # Settings: camelCase → snake_case translation
    assert body["settings"]["name"] == "North & Pine"
    assert body["settings"]["logo_text"] == "North & Pine"
    assert body["settings"]["primary_color"] == "#1f4fd1"
    assert body["settings"]["theme_mode"] == "light"
    assert body["settings"]["radius"] == 10
    assert body["settings"]["contact_email"] == "studio@example.com"
    assert body["settings"]["contact_hours"] == "Mon-Thu 9-5"

    # List entities present with translated content
    assert len(body["navigation"]) == 2
    assert body["navigation"][0]["label"] == "Home"

    assert len(body["sections"]) == 1
    assert body["sections"][0]["type"] == "hero"
    # Section type-specific extras stashed in payload
    assert body["sections"][0]["payload"]["stats"][0]["label"] == "Projects"

    assert len(body["projects"]) == 1
    assert body["projects"][0]["title"] == "Field & Garden rebrand"
    # url -> external_url
    assert body["projects"][0]["external_url"] == "https://example.com/fg"
    # Slug derived from title
    assert body["projects"][0]["slug"]

    assert len(body["posts"]) == 1
    assert body["posts"][0]["slug"] == "why-smallest"
    # publishDate -> publish_date (ISO datetime string)
    assert body["posts"][0]["publish_date"].startswith("2026-04-22")

    assert len(body["services"]) == 1
    assert body["services"][0]["title"] == "Brand Identity"

    # FAQs use {q, a} in SiteForge; importer translates to question/answer.
    assert len(body["faqs"]) == 1
    assert body["faqs"][0]["question"] == "How long?"
    assert body["faqs"][0]["answer"] == "Six weeks."

    assert len(body["team"]) == 1
    assert body["team"][0]["name"] == "Eve Halden"

    assert len(body["testimonials"]) == 1
    assert len(body["social_links"]) == 1


# ---------------------------------------------------------------------------
# Malformed JSON / missing keys
# ---------------------------------------------------------------------------
def test_import_siteforge_rejects_malformed_json(client, auth_headers, db):
    _wipe_all_marketing(db)
    r = _upload(client, auth_headers, b"not-json-at-all{{{")
    assert r.status_code == 400, r.text
    assert "json" in r.json()["detail"].lower()


def test_import_siteforge_rejects_missing_required_keys(client, auth_headers, db):
    _wipe_all_marketing(db)
    bad = {"siteSettings": {}, "themeSettings": {}}  # missing sections + projects
    r = _upload(client, auth_headers, bad)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"].lower()
    assert "missing" in detail
    assert "sections" in detail or "projects" in detail


def test_import_siteforge_rejects_empty_upload(client, auth_headers, db):
    _wipe_all_marketing(db)
    files = {"file": ("empty.json", io.BytesIO(b""), "application/json")}
    r = client.post(f"{API}/import-siteforge", headers=auth_headers, files=files)
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Role gating — Employee must be rejected
# ---------------------------------------------------------------------------
def test_import_siteforge_rejects_non_admin(client, db):
    _wipe_all_marketing(db)
    # Create a fresh employee account so this isn't dependent on test order.
    email = "marketing-sf-emp@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "SF Emp", "password": "AbcDefGh12"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "AbcDefGh12"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    r = _upload(client, headers, _minimal_siteforge_export())
    assert r.status_code == 403, r.text
    assert r.json().get("code") == "permission_denied"


# ---------------------------------------------------------------------------
# Idempotency: running twice with wipe_existing=true replaces, not duplicates
# ---------------------------------------------------------------------------
def test_import_siteforge_twice_wipes_first(client, auth_headers, db):
    _wipe_all_marketing(db)

    # First import: 1 project
    r1 = _upload(client, auth_headers, _minimal_siteforge_export())
    assert r1.status_code == 200
    body1 = r1.json()
    assert len(body1["projects"]) == 1
    first_project_id = body1["projects"][0]["id"]
    assert body1["settings"]["name"] == "North & Pine"

    # Second import with different content
    payload = _minimal_siteforge_export()
    payload["siteSettings"]["name"] = "Second Studio"
    payload["projects"].append({
        "id": "p_2", "title": "Second project", "client": "X", "category": "Web",
        "summary": "", "body": "", "year": "2026", "tags": [], "featured": False,
        "url": "",
    })
    r2 = _upload(client, auth_headers, payload)
    assert r2.status_code == 200
    body2 = r2.json()
    # Settings updated in place (singleton)
    assert body2["settings"]["name"] == "Second Studio"
    # Old project gone, new ones in
    assert len(body2["projects"]) == 2
    project_ids = {p["id"] for p in body2["projects"]}
    assert first_project_id not in project_ids
    # Settings row count still 1 (singleton not duplicated)
    assert len(db.scalars(select(MarketingSettings)).all()) == 1


# ---------------------------------------------------------------------------
# Service-level: drops SiteForge-only fields silently
# ---------------------------------------------------------------------------
def test_apply_siteforge_export_drops_activity_and_checklist(db):
    _wipe_all_marketing(db)
    state = svc.apply_siteforge_export(db, _minimal_siteforge_export(), wipe_existing=True)
    # No model for activity/launchChecklist — they're not persisted anywhere,
    # but the import must succeed despite the keys being present in the payload.
    assert state.settings.name == "North & Pine"
    assert len(state.projects) == 1
