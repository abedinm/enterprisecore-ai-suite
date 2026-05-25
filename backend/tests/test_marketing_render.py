"""Marketing Site Builder — public renderer.

Verifies that ``/site/`` and friends render HTML, that drafts hide on the
blog index, that a real project slug resolves while a bogus one 404s, and
that ``/site/sitemap.xml`` produces parseable XML.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET


API = "/api/v1/marketing"


def _set_name(client, auth_headers, name: str = "Public Site Test Co"):
    """Give the install a recognisable name so we can assert it appears in
    rendered HTML."""
    r = client.patch(
        f"{API}/settings", headers=auth_headers, json={"name": name},
    )
    assert r.status_code == 200, r.text
    return name


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
def test_site_home_renders_html_with_site_name(client, auth_headers):
    name = _set_name(client, auth_headers, "Render Test Studio")
    r = client.get("/site/")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert name in r.text
    # Cache-Control must be set on rendered pages
    assert r.headers.get("cache-control") == "public, max-age=60"


# ---------------------------------------------------------------------------
# Project detail by slug — real + bogus
# ---------------------------------------------------------------------------
def test_site_project_detail_by_slug(client, auth_headers):
    _set_name(client, auth_headers)
    title = "Halden Counsel website"
    r = client.post(
        f"{API}/projects", headers=auth_headers,
        json={
            "title": title,
            "client": "Halden Counsel",
            "summary": "Editorial law firm site.",
            "body": "First paragraph here.\n\nSecond paragraph here.",
            "featured": True,
        },
    )
    assert r.status_code == 201, r.text
    slug = r.json()["slug"]

    r = client.get(f"/site/portfolio/{slug}")
    assert r.status_code == 200
    assert title in r.text
    assert "Editorial law firm site." in r.text


def test_site_project_detail_bogus_slug_returns_404(client, auth_headers):
    _set_name(client, auth_headers)
    r = client.get("/site/portfolio/this-project-does-not-exist")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Blog list — drafts hidden
# ---------------------------------------------------------------------------
def test_site_blog_hides_drafts(client, auth_headers):
    _set_name(client, auth_headers)
    pub = client.post(
        f"{API}/posts", headers=auth_headers,
        json={"title": "Published render test post", "status": "published"},
    )
    drf = client.post(
        f"{API}/posts", headers=auth_headers,
        json={"title": "Draft secret render test post", "status": "draft"},
    )
    assert pub.status_code == 201 and drf.status_code == 201

    r = client.get("/site/blog")
    assert r.status_code == 200
    assert "Published render test post" in r.text
    assert "Draft secret render test post" not in r.text

    # The published slug resolves; the draft one 404s
    pub_slug = pub.json()["slug"]
    drf_slug = drf.json()["slug"]
    r2 = client.get(f"/site/blog/{pub_slug}")
    assert r2.status_code == 200
    r3 = client.get(f"/site/blog/{drf_slug}")
    assert r3.status_code == 404


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------
def test_site_sitemap_xml_is_valid(client, auth_headers):
    # Set base_url so the sitemap uses it
    r = client.patch(
        f"{API}/settings", headers=auth_headers,
        json={"base_url": "https://render.test"},
    )
    assert r.status_code == 200

    r = client.get("/site/sitemap.xml")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml")

    # Parse the XML to confirm validity + at least one <url>
    root = ET.fromstring(r.text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = root.findall("sm:url", ns)
    assert len(urls) >= 6  # 6 static pages minimum
    locs = {u.find("sm:loc", ns).text for u in urls}
    # Static pages all present
    for path in ("/site/", "/site/about", "/site/services",
                 "/site/portfolio", "/site/blog", "/site/contact"):
        assert any(loc.endswith(path) for loc in locs), f"missing {path} in sitemap"
    # Caching header
    assert "max-age" in r.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# Other rendered pages — smoke test
# ---------------------------------------------------------------------------
def test_site_other_pages_render(client, auth_headers):
    _set_name(client, auth_headers)
    for path in ("/site/about", "/site/services", "/site/portfolio",
                 "/site/contact"):
        r = client.get(path)
        assert r.status_code == 200, f"{path}: {r.text[:200]}"
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers.get("cache-control") == "public, max-age=60"
