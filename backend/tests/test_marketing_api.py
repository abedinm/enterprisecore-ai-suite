"""Marketing Site Builder — admin/editor API.

Covers state hydration, settings singleton, CRUD for projects/posts/services,
reorder, image upload (allowed + rejected), launch checklist, plan gating.
"""
from __future__ import annotations

import io


API = "/api/v1/marketing"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _png_bytes(size: int = 32) -> bytes:
    """Build a tiny in-memory PNG so the upload tests don't need a fixture file."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=(80, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# State + settings
# ---------------------------------------------------------------------------
def test_get_state_on_fresh_install_returns_seeded_empty_state(client, auth_headers):
    r = client.get(f"{API}/state", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Every top-level key is present
    expected_keys = {
        "settings", "navigation", "sections", "projects", "posts", "services",
        "testimonials", "faqs", "team", "social_links", "uploads",
    }
    assert expected_keys.issubset(body.keys())
    # Settings singleton was seeded by init_db
    assert body["settings"]["key"] == "default"
    # Theme defaults match the model
    assert body["settings"]["primary_color"] == "#1f4fd1"
    assert body["settings"]["theme_mode"] == "light"
    # No demo content — start blank
    assert body["sections"] == []
    assert body["projects"] == []
    assert body["posts"] == []


def test_patch_settings_updates_singleton(client, auth_headers):
    r = client.patch(
        f"{API}/settings",
        headers=auth_headers,
        json={
            "name": "Acme Studio",
            "tagline": "We build things",
            "primary_color": "#ff5500",
            "contact_email": "hello@acme.test",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Acme Studio"
    assert body["tagline"] == "We build things"
    assert body["primary_color"] == "#ff5500"
    assert body["contact_email"] == "hello@acme.test"

    # Persisted across requests
    r2 = client.get(f"{API}/settings", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["primary_color"] == "#ff5500"


# ---------------------------------------------------------------------------
# Project CRUD + slug uniqueness
# ---------------------------------------------------------------------------
def test_project_crud_round_trip(client, auth_headers):
    r = client.post(
        f"{API}/projects",
        headers=auth_headers,
        json={
            "title": "Field & Garden rebrand",
            "client": "Field & Garden Co.",
            "category": "Identity",
            "summary": "A warm identity refresh.",
            "tags": ["identity", "print"],
            "featured": True,
        },
    )
    assert r.status_code == 201, r.text
    project = r.json()
    assert project["slug"] == "field-garden-rebrand"
    assert project["featured"] is True
    pid = project["id"]

    # PATCH
    r = client.patch(
        f"{API}/projects/{pid}",
        headers=auth_headers,
        json={"summary": "Updated summary", "featured": False},
    )
    assert r.status_code == 200
    assert r.json()["summary"] == "Updated summary"
    assert r.json()["featured"] is False

    # LIST
    r = client.get(f"{API}/projects", headers=auth_headers)
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())

    # DELETE
    r = client.delete(f"{API}/projects/{pid}", headers=auth_headers)
    assert r.status_code == 204
    r = client.get(f"{API}/projects", headers=auth_headers)
    assert all(p["id"] != pid for p in r.json())


def test_project_slug_uniqueness(client, auth_headers):
    r1 = client.post(
        f"{API}/projects", headers=auth_headers,
        json={"title": "My Project"},
    )
    r2 = client.post(
        f"{API}/projects", headers=auth_headers,
        json={"title": "My Project"},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["slug"] != r2.json()["slug"]
    assert r1.json()["slug"] == "my-project"
    assert r2.json()["slug"].startswith("my-project-")


# ---------------------------------------------------------------------------
# Post CRUD
# ---------------------------------------------------------------------------
def test_post_crud_round_trip(client, auth_headers):
    r = client.post(
        f"{API}/posts",
        headers=auth_headers,
        json={
            "title": "Hello world",
            "excerpt": "First post",
            "body": "This is a post body.\n\nSecond paragraph.",
            "status": "draft",
        },
    )
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["slug"] == "hello-world"
    assert post["status"] == "draft"

    # Publish + change title (which re-slugs)
    r = client.patch(
        f"{API}/posts/{post['id']}",
        headers=auth_headers,
        json={"title": "Hello there", "status": "published"},
    )
    assert r.status_code == 200
    assert r.json()["slug"] == "hello-there"
    assert r.json()["status"] == "published"


# ---------------------------------------------------------------------------
# Service CRUD
# ---------------------------------------------------------------------------
def test_service_crud_round_trip(client, auth_headers):
    r = client.post(
        f"{API}/services",
        headers=auth_headers,
        json={
            "title": "Brand identity",
            "summary": "Marks and systems",
            "price": "from $9,800",
            "featured": True,
        },
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = client.patch(
        f"{API}/services/{sid}", headers=auth_headers,
        json={"price": "from $10,000"},
    )
    assert r.status_code == 200
    assert r.json()["price"] == "from $10,000"

    r = client.delete(f"{API}/services/{sid}", headers=auth_headers)
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------
def test_reorder_services(client, auth_headers):
    created = []
    for name in ("A", "B", "C"):
        r = client.post(
            f"{API}/services", headers=auth_headers,
            json={"title": name, "order": 0},
        )
        assert r.status_code == 201
        created.append(r.json()["id"])

    payload = [
        {"id": created[0], "order": 30},
        {"id": created[1], "order": 10},
        {"id": created[2], "order": 20},
    ]
    r = client.put(
        f"{API}/services/reorder", headers=auth_headers, json=payload,
    )
    assert r.status_code == 200
    rows = r.json()
    by_id = {row["id"]: row["order"] for row in rows}
    assert by_id[created[0]] == 30
    assert by_id[created[1]] == 10
    assert by_id[created[2]] == 20


# ---------------------------------------------------------------------------
# Navigation — bulk replace
# ---------------------------------------------------------------------------
def test_navigation_bulk_replace(client, auth_headers):
    nav = [
        {"label": "Home", "route": "home", "enabled": True, "order": 0},
        {"label": "Work", "route": "portfolio", "enabled": True, "order": 1},
        {"label": "Journal", "route": "blog", "enabled": False, "order": 2},
    ]
    r = client.put(f"{API}/navigation", headers=auth_headers, json=nav)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 3
    assert [n["route"] for n in rows] == ["home", "portfolio", "blog"]
    assert [n["enabled"] for n in rows] == [True, True, False]

    # A second PUT atomically replaces — old rows gone
    nav2 = [{"label": "Only Home", "route": "home", "enabled": True, "order": 0}]
    r2 = client.put(f"{API}/navigation", headers=auth_headers, json=nav2)
    assert r2.status_code == 200
    rows2 = r2.json()
    assert len(rows2) == 1
    assert rows2[0]["label"] == "Only Home"


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------
def test_upload_accepts_small_png(client, auth_headers):
    raw = _png_bytes(32)
    r = client.post(
        f"{API}/uploads",
        headers=auth_headers,
        files={"file": ("test.png", raw, "image/png")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "test.png"
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] > 0
    assert body["storage_path"].startswith("uploads/marketing/")


def test_upload_rejects_wrong_mime(client, auth_headers):
    r = client.post(
        f"{API}/uploads",
        headers=auth_headers,
        files={"file": ("bad.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 422
    assert "Unsupported file type" in r.json()["detail"]


def test_upload_rejects_oversize(client, auth_headers):
    # Make a >2MB payload pretending to be PNG. We need the MIME to pass the
    # allowlist check so the size check actually fires; the bytes don't have to
    # be a valid PNG because the size cap is checked before Pillow opens it.
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)
    r = client.post(
        f"{API}/uploads",
        headers=auth_headers,
        files={"file": ("huge.png", raw, "image/png")},
    )
    assert r.status_code == 422
    assert "too large" in r.json()["detail"]


def test_uploads_list_and_delete(client, auth_headers):
    raw = _png_bytes(16)
    r = client.post(
        f"{API}/uploads",
        headers=auth_headers,
        files={"file": ("u.png", raw, "image/png")},
    )
    assert r.status_code == 201
    uid = r.json()["id"]

    r = client.get(f"{API}/uploads", headers=auth_headers)
    assert r.status_code == 200
    ids = {u["id"] for u in r.json()}
    assert uid in ids

    r = client.delete(f"{API}/uploads/{uid}", headers=auth_headers)
    assert r.status_code == 204

    r = client.get(f"{API}/uploads", headers=auth_headers)
    assert all(u["id"] != uid for u in r.json())


# ---------------------------------------------------------------------------
# Launch checklist — completion rises as content is added
# ---------------------------------------------------------------------------
def test_launch_checklist_rises_with_content(client, auth_headers, db):
    # Start from a clean slate inside this test by deleting any leftovers
    # from earlier tests in the same session.
    from app.models.marketing import (
        MarketingPost, MarketingProject, MarketingService,
        MarketingSocialLink, MarketingTestimonial,
    )
    for model in (MarketingService, MarketingProject, MarketingPost,
                  MarketingTestimonial, MarketingSocialLink):
        db.query(model).delete()
    db.commit()

    # Reset settings to defaults (name/colors empty)
    client.patch(
        f"{API}/settings", headers=auth_headers,
        json={"name": "", "tagline": "", "contact_email": "",
              "primary_color": "#1f4fd1", "accent_color": "#0f172a"},
    )

    r = client.get(f"{API}/launch-checklist", headers=auth_headers)
    assert r.status_code == 200
    initial = r.json()
    # On a blank slate nothing should be done
    assert all(item["done"] is False for item in initial)

    # Add the site name + tagline, a non-default primary color, contact email,
    # 3 services, 3 projects, 1 published post, 2 testimonials, 1 social link.
    client.patch(
        f"{API}/settings", headers=auth_headers,
        json={
            "name": "Acme", "tagline": "Studio",
            "contact_email": "x@y.test",
            "primary_color": "#ff0000",
        },
    )
    for i in range(3):
        client.post(f"{API}/services", headers=auth_headers, json={"title": f"S{i}"})
        client.post(f"{API}/projects", headers=auth_headers, json={"title": f"P{i}"})
    client.post(
        f"{API}/posts", headers=auth_headers,
        json={"title": "Published one", "status": "published"},
    )
    for i in range(2):
        client.post(
            f"{API}/testimonials", headers=auth_headers,
            json={"quote": f"Quote {i}", "author": "Someone"},
        )
    client.post(
        f"{API}/social-links", headers=auth_headers,
        json={"platform": "twitter", "url": "https://twitter.com/acme"},
    )

    r = client.get(f"{API}/launch-checklist", headers=auth_headers)
    assert r.status_code == 200
    final = r.json()
    # Every item should now be done
    for item in final:
        assert item["done"] is True, f"{item['id']} still not done"


# ---------------------------------------------------------------------------
# Plan gating — strip 'marketing' from every plan, expect 403
# ---------------------------------------------------------------------------
def test_marketing_gated_off_when_feature_removed(client, auth_headers, monkeypatch):
    from app.core import plans as plans_mod

    patched = {plan: set(feats) for plan, feats in plans_mod.PLAN_FEATURES.items()}
    for feats in patched.values():
        feats.discard("marketing")
    monkeypatch.setattr(plans_mod, "PLAN_FEATURES", patched)

    r = client.get(f"{API}/state", headers=auth_headers)
    assert r.status_code == 403
    assert r.json().get("code") == "permission_denied"

    r2 = client.get(f"{API}/projects", headers=auth_headers)
    assert r2.status_code == 403

    # Public site is also gated
    r3 = client.get("/site/")
    assert r3.status_code == 403
