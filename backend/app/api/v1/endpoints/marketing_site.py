"""Marketing Site Builder — public-facing rendered HTML.

This router renders the customer's marketing site itself: home / about /
services / portfolio / blog / contact. It's plan-gated (the whole marketing
module disappears on plans without the feature) but does NOT require auth —
the rendered pages are meant to be served to anonymous visitors.

Mounted at ``/site`` from ``app.main`` (outside ``/api/v1``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_plan_feature
from app.core.config import settings as app_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.marketing import (
    MarketingFAQ, MarketingNavItem, MarketingPost, MarketingProject,
    MarketingSection, MarketingService, MarketingSocialLink,
    MarketingTeamMember, MarketingTestimonial, MarketingUpload,
)
from app.services import marketing as svc

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Pages are cached for one minute at the edge. Short enough that a creator
# can refresh after editing and see changes; long enough to absorb a small
# burst of visitors without hitting the DB on every request.
_CACHE_CONTROL = "public, max-age=60"

router = APIRouter(dependencies=[Depends(require_plan_feature("marketing"))])


# ---------------------------------------------------------------------------
# Shared context builder
# ---------------------------------------------------------------------------
def _common_context(db: Session) -> dict:
    """Build the dict passed into every template — settings + nav + footer."""
    settings = svc.get_settings(db)
    nav = db.scalars(
        select(MarketingNavItem).order_by(MarketingNavItem.order, MarketingNavItem.created_at)
    ).all()
    social = db.scalars(
        select(MarketingSocialLink).order_by(
            MarketingSocialLink.order, MarketingSocialLink.created_at
        )
    ).all()
    return {"settings": settings, "navigation": nav, "social_links": social}


def _split_body(body: str) -> list[str]:
    """Split a free-form body into paragraphs.

    SiteForge stores post/project bodies as Markdown-ish text with blank-line
    separators. We avoid pulling in a Markdown dependency — the public render
    only needs a plain paragraph split that handles ``\\n\\n`` correctly. The
    post template handles a leading ``# `` or ``## `` per paragraph as a
    heading. Inline formatting is rendered verbatim, which is fine for a
    minimal portfolio site.
    """
    if not body:
        return []
    parts = [p.strip() for p in body.replace("\r\n", "\n").split("\n\n")]
    return [p for p in parts if p]


def _set_cache(resp: Response) -> None:
    resp.headers["Cache-Control"] = _CACHE_CONTROL


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def render_home(request: Request, db: Session = Depends(get_db)):
    ctx = _common_context(db)
    ctx["sections"] = db.scalars(
        select(MarketingSection).order_by(MarketingSection.order, MarketingSection.created_at)
    ).all()
    ctx["projects"] = db.scalars(
        select(MarketingProject)
        .where(MarketingProject.featured == True)  # noqa: E712
        .order_by(MarketingProject.order, MarketingProject.created_at)
    ).all() or db.scalars(
        select(MarketingProject).order_by(MarketingProject.order, MarketingProject.created_at)
    ).all()
    ctx["services"] = db.scalars(
        select(MarketingService).order_by(MarketingService.order, MarketingService.created_at)
    ).all()
    ctx["testimonials"] = db.scalars(
        select(MarketingTestimonial).order_by(
            MarketingTestimonial.order, MarketingTestimonial.created_at
        )
    ).all()
    ctx["active"] = "home"
    resp = templates.TemplateResponse(request, "marketing/home.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def render_about(request: Request, db: Session = Depends(get_db)):
    ctx = _common_context(db)
    ctx["sections"] = db.scalars(select(MarketingSection)).all()
    ctx["team"] = db.scalars(
        select(MarketingTeamMember).order_by(
            MarketingTeamMember.order, MarketingTeamMember.created_at
        )
    ).all()
    ctx["faqs"] = db.scalars(
        select(MarketingFAQ).order_by(MarketingFAQ.order, MarketingFAQ.created_at)
    ).all()
    ctx["active"] = "about"
    resp = templates.TemplateResponse(request, "marketing/about.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/services", response_class=HTMLResponse, include_in_schema=False)
def render_services(request: Request, db: Session = Depends(get_db)):
    ctx = _common_context(db)
    ctx["services"] = db.scalars(
        select(MarketingService).order_by(MarketingService.order, MarketingService.created_at)
    ).all()
    ctx["active"] = "services"
    resp = templates.TemplateResponse(request, "marketing/services.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/portfolio", response_class=HTMLResponse, include_in_schema=False)
def render_portfolio(request: Request, db: Session = Depends(get_db)):
    ctx = _common_context(db)
    ctx["projects"] = db.scalars(
        select(MarketingProject).order_by(MarketingProject.order, MarketingProject.created_at)
    ).all()
    ctx["active"] = "portfolio"
    resp = templates.TemplateResponse(request, "marketing/portfolio.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/portfolio/{slug}", response_class=HTMLResponse, include_in_schema=False)
def render_project(slug: str, request: Request, db: Session = Depends(get_db)):
    project = db.scalar(select(MarketingProject).where(MarketingProject.slug == slug))
    if project is None:
        raise NotFoundError("Project not found")
    ctx = _common_context(db)
    ctx["project"] = project
    ctx["body_paragraphs"] = _split_body(project.body)
    ctx["active"] = "portfolio"
    resp = templates.TemplateResponse(request, "marketing/project.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/blog", response_class=HTMLResponse, include_in_schema=False)
def render_blog(request: Request, db: Session = Depends(get_db)):
    ctx = _common_context(db)
    # Drafts are intentionally not shown publicly.
    ctx["posts"] = db.scalars(
        select(MarketingPost)
        .where(MarketingPost.status == "published")
        .order_by(MarketingPost.publish_date.desc().nullslast(), MarketingPost.created_at.desc())
    ).all()
    ctx["active"] = "blog"
    resp = templates.TemplateResponse(request, "marketing/blog.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/blog/{slug}", response_class=HTMLResponse, include_in_schema=False)
def render_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.scalar(
        select(MarketingPost).where(
            MarketingPost.slug == slug, MarketingPost.status == "published"
        )
    )
    if post is None:
        raise NotFoundError("Post not found")
    ctx = _common_context(db)
    ctx["post"] = post
    ctx["body_paragraphs"] = _split_body(post.body)
    ctx["active"] = "blog"
    resp = templates.TemplateResponse(request, "marketing/post.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/contact", response_class=HTMLResponse, include_in_schema=False)
def render_contact(request: Request, db: Session = Depends(get_db)):
    ctx = _common_context(db)
    ctx["active"] = "contact"
    resp = templates.TemplateResponse(request, "marketing/contact.html", ctx)
    _set_cache(resp)
    return resp


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request, db: Session = Depends(get_db)) -> Response:
    """Minimal XML sitemap of every public URL.

    Uses the configured ``base_url`` from MarketingSettings if set; otherwise
    falls back to ``str(request.base_url)`` so the sitemap still validates."""
    settings = svc.get_settings(db)
    base = (settings.base_url or str(request.base_url)).rstrip("/")
    today = datetime.now(timezone.utc).date().isoformat()

    static_paths = ["/site/", "/site/about", "/site/services",
                    "/site/portfolio", "/site/blog", "/site/contact"]
    projects = db.scalars(
        select(MarketingProject).order_by(MarketingProject.created_at)
    ).all()
    posts = db.scalars(
        select(MarketingPost).where(MarketingPost.status == "published")
    ).all()

    urls: list[str] = []
    for p in static_paths:
        urls.append(f"<url><loc>{base}{p}</loc><lastmod>{today}</lastmod></url>")
    for proj in projects:
        urls.append(
            f"<url><loc>{base}/site/portfolio/{proj.slug}</loc>"
            f"<lastmod>{today}</lastmod></url>"
        )
    for post in posts:
        urls.append(
            f"<url><loc>{base}/site/blog/{post.slug}</loc>"
            f"<lastmod>{today}</lastmod></url>"
        )

    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(content=body, media_type="application/xml",
                    headers={"Cache-Control": _CACHE_CONTROL})


@router.get("/uploads/{upload_id}", include_in_schema=False)
def serve_upload(upload_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serve a media-library image by id.

    Files live under ``storage/uploads/marketing/...`` and aren't exposed via
    the regular ``/files`` mount because their URLs need to embed a stable id
    rather than a path-on-disk.
    """
    upload = db.get(MarketingUpload, upload_id)
    if upload is None:
        raise NotFoundError("Upload not found")
    absolute = app_settings.storage_dir / upload.storage_path
    if not absolute.exists():
        raise NotFoundError("Upload file missing")
    return FileResponse(
        path=str(absolute),
        media_type=upload.content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )
