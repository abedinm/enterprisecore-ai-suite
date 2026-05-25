"""Marketing Site Builder — pure business logic.

HTTP handlers in ``app/api/v1/endpoints/marketing.py`` and the public renderer
in ``app/api/v1/endpoints/marketing_site.py`` both call into these helpers.
Keeping the policy here (seeding, slug generation, image storage, launch
checklist) means the test surface is small and framework-free.
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone  # noqa: F401 — also used by SiteForge import
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.exceptions import ValidationFailed
from app.models.marketing import (
    MarketingFAQ, MarketingNavItem, MarketingPost, MarketingProject,
    MarketingSection, MarketingService, MarketingSettings, MarketingSocialLink,
    MarketingTeamMember, MarketingTestimonial, MarketingUpload,
)
from app.schemas.marketing import (
    FAQOut, LaunchChecklistItem, MarketingSettingsOut, MarketingStateOut,
    MarketingUploadOut, NavItemOut, PostOut, ProjectOut, SectionOut,
    ServiceOut, SocialLinkOut, TeamMemberOut, TestimonialOut,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MARKETING_UPLOAD_DIR = "marketing"
ALLOWED_IMAGE_TYPES: set[str] = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB raw upload cap (matches avatars)
IMAGE_MAX_DIM = 1600  # downscale longest side to keep storage predictable

# Settings singleton key — there is exactly one row, keyed by this string.
SETTINGS_KEY = "default"

# Theme defaults — used by the launch checklist to detect "still on defaults".
_DEFAULT_PRIMARY = "#1f4fd1"
_DEFAULT_ACCENT = "#0f172a"


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9\-]+")
_SLUG_DASH_RE = re.compile(r"-{2,}")


def slugify(value: str) -> str:
    """Lowercase, ASCII-safe, hyphen-joined slug. Empty input → empty string."""
    if not value:
        return ""
    # Strip accents (NFKD then drop combining chars) so e.g. "résumé" → "resume".
    normalised = unicodedata.normalize("NFKD", value)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower().strip()
    # Spaces / underscores / odd punctuation become hyphens.
    hyphened = re.sub(r"[\s_]+", "-", lowered)
    cleaned = _SLUG_STRIP_RE.sub("", hyphened)
    cleaned = _SLUG_DASH_RE.sub("-", cleaned).strip("-")
    return cleaned or "untitled"


def unique_slug(db: Session, model_cls, base: str, *, exclude_id: str | None = None) -> str:
    """Return ``base`` if free, else ``base-2``, ``base-3``... up to ``base-999``.

    ``exclude_id`` lets callers update an existing row without colliding with
    its own current slug.
    """
    candidate = base
    suffix = 2
    while True:
        stmt = select(model_cls).where(model_cls.slug == candidate)
        if exclude_id:
            stmt = stmt.where(model_cls.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1
        if suffix > 999:  # pragma: no cover — pathological
            return f"{base}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Settings singleton
# ---------------------------------------------------------------------------
def get_settings(db: Session) -> MarketingSettings:
    """Fetch the singleton settings row for the current tenant, creating
    an empty one if missing.

    The settings table is keyed by id now (was ``key="default"`` in the
    single-tenant era) plus a uniqueness constraint on
    ``(tenant_id, key)``. We look up by ``key=SETTINGS_KEY`` and rely on
    the tenant auto-filter to restrict to the current tenant's row.
    """
    row = db.scalar(select(MarketingSettings).where(MarketingSettings.key == SETTINGS_KEY))
    if row is None:
        row = MarketingSettings(key=SETTINGS_KEY)
        db.add(row)
        db.flush()
    return row


# ---------------------------------------------------------------------------
# Full-state hydration
# ---------------------------------------------------------------------------
def get_full_state(db: Session) -> MarketingStateOut:
    """One bundled payload of every marketing entity.

    The Studio editor calls this once on mount and the public renderer calls
    it on every render (cached behind a short HTTP TTL). Returning everything
    in one shape avoids 10+ round-trips and keeps the renderer simple.
    """
    s = get_settings(db)

    nav_rows = db.scalars(
        select(MarketingNavItem).order_by(MarketingNavItem.order, MarketingNavItem.created_at)
    ).all()
    section_rows = db.scalars(
        select(MarketingSection).order_by(MarketingSection.order, MarketingSection.created_at)
    ).all()
    project_rows = db.scalars(
        select(MarketingProject).order_by(MarketingProject.order, MarketingProject.created_at)
    ).all()
    post_rows = db.scalars(
        select(MarketingPost).order_by(
            MarketingPost.publish_date.desc().nullslast(),
            MarketingPost.created_at.desc(),
        )
    ).all()
    service_rows = db.scalars(
        select(MarketingService).order_by(MarketingService.order, MarketingService.created_at)
    ).all()
    test_rows = db.scalars(
        select(MarketingTestimonial).order_by(
            MarketingTestimonial.order, MarketingTestimonial.created_at
        )
    ).all()
    faq_rows = db.scalars(
        select(MarketingFAQ).order_by(MarketingFAQ.order, MarketingFAQ.created_at)
    ).all()
    team_rows = db.scalars(
        select(MarketingTeamMember).order_by(MarketingTeamMember.order, MarketingTeamMember.created_at)
    ).all()
    social_rows = db.scalars(
        select(MarketingSocialLink).order_by(MarketingSocialLink.order, MarketingSocialLink.created_at)
    ).all()
    upload_rows = db.scalars(
        select(MarketingUpload).order_by(MarketingUpload.created_at.desc())
    ).all()

    return MarketingStateOut(
        settings=MarketingSettingsOut.model_validate(s),
        navigation=[NavItemOut.model_validate(r) for r in nav_rows],
        sections=[SectionOut.model_validate(r) for r in section_rows],
        projects=[ProjectOut.model_validate(r) for r in project_rows],
        posts=[PostOut.model_validate(r) for r in post_rows],
        services=[ServiceOut.model_validate(r) for r in service_rows],
        testimonials=[TestimonialOut.model_validate(r) for r in test_rows],
        faqs=[FAQOut.model_validate(r) for r in faq_rows],
        team=[TeamMemberOut.model_validate(r) for r in team_rows],
        social_links=[SocialLinkOut.model_validate(r) for r in social_rows],
        uploads=[MarketingUploadOut.model_validate(r) for r in upload_rows],
    )


# ---------------------------------------------------------------------------
# Launch checklist
# ---------------------------------------------------------------------------
def compute_launch_checklist(state: MarketingStateOut) -> list[LaunchChecklistItem]:
    """Derive the 8 readiness flags from the current state.

    Matches SiteForge's ``launchChecklist`` shape: stable ids the editor can
    pin in the UI, plus a ``done`` flag computed server-side from data
    presence. The frontend doesn't need to know the rules.
    """
    s = state.settings
    published_posts = [p for p in state.posts if p.status == "published"]

    items = [
        ("siteName", "Site name & tagline set",
         bool(s.name.strip() and s.tagline.strip())),
        ("brandColors", "Brand colors customized",
         s.primary_color.lower() != _DEFAULT_PRIMARY.lower()
         or s.accent_color.lower() != _DEFAULT_ACCENT.lower()),
        ("services", "At least 3 services added", len(state.services) >= 3),
        ("projects", "At least 3 projects added", len(state.projects) >= 3),
        ("posts", "At least 1 published post", len(published_posts) >= 1),
        ("testimonials", "At least 2 testimonials", len(state.testimonials) >= 2),
        ("contact", "Contact email set", bool(s.contact_email.strip())),
        ("social", "Social links added", len(state.social_links) >= 1),
    ]
    return [LaunchChecklistItem(id=cid, label=label, done=done)
            for cid, label, done in items]


# ---------------------------------------------------------------------------
# Image upload — MIME allowlist + size cap + EXIF strip via re-encode
# ---------------------------------------------------------------------------
def _marketing_storage_dir() -> Path:
    """``storage/uploads/marketing/YYYY-MM/``, created on demand."""
    now = datetime.now(timezone.utc)
    bucket = f"{now.year:04d}-{now.month:02d}"
    d = app_settings.storage_dir / "uploads" / MARKETING_UPLOAD_DIR / bucket
    d.mkdir(parents=True, exist_ok=True)
    return d


def _relative_storage_path(absolute: Path) -> str:
    """Render ``storage_path`` as a POSIX-style path under ``storage/``."""
    rel = absolute.relative_to(app_settings.storage_dir)
    return rel.as_posix()


def save_upload(
    db: Session,
    *,
    user_id: str | None,
    filename: str,
    content_type: str,
    raw: bytes,
) -> MarketingUpload:
    """Validate, re-encode, save to disk, and record a ``MarketingUpload`` row.

    The re-encode step normalises the file (PNG output, capped longest side)
    and incidentally strips EXIF / ICC / other metadata that could leak
    location or device info from an uploaded photo.
    """
    ct = (content_type or "").lower()
    if ct not in ALLOWED_IMAGE_TYPES:
        raise ValidationFailed(
            f"Unsupported file type {ct!r}. Allowed: PNG, JPEG, WEBP."
        )
    if not raw:
        raise ValidationFailed("Empty upload.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValidationFailed(
            f"Image is too large ({len(raw)} bytes). "
            f"Max {MAX_IMAGE_BYTES // 1024} KB."
        )

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover
        raise ValidationFailed("Pillow is required for image uploads on the server") from exc

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ValidationFailed("File is not a recognisable image") from exc

    img.thumbnail((IMAGE_MAX_DIM, IMAGE_MAX_DIM))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")

    upload_id = uuid.uuid4().hex
    storage_dir = _marketing_storage_dir()
    storage_path = storage_dir / f"{upload_id}.png"
    img.save(storage_path, format="PNG", optimize=True)

    rec = MarketingUpload(
        id=upload_id,
        filename=Path(filename or "image.png").name[:500],
        content_type="image/png",
        size_bytes=storage_path.stat().st_size,
        storage_path=_relative_storage_path(storage_path),
        uploaded_by_id=user_id,
    )
    db.add(rec)
    db.flush()
    return rec


def delete_upload(db: Session, upload: MarketingUpload) -> None:
    """Best-effort delete: drop the row, then unlink the file. File-system
    failures don't roll back the DB delete — the row is the source of truth
    and an orphan PNG on disk is harmless."""
    abs_path = app_settings.storage_dir / upload.storage_path
    db.delete(upload)
    db.flush()
    try:
        abs_path.unlink(missing_ok=True)
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# First-boot seed — empty but valid state
# ---------------------------------------------------------------------------
def seed_default_marketing_state(db: Session) -> None:
    """Ensure the singleton settings row exists.

    Deliberately does NOT seed demo content — projects, posts, services, etc.
    start empty so the first-run experience is "your blank canvas", not "delete
    the demo studio's content before you can use it". Industry templates are a
    separate Phase 3 feature.
    """
    if db.scalar(select(MarketingSettings).where(MarketingSettings.key == SETTINGS_KEY)) is None:
        db.add(MarketingSettings(key=SETTINGS_KEY))
        db.flush()


# ---------------------------------------------------------------------------
# Industry templates (Phase 3)
#
# Templates are static JSON files shipped with the backend. Each file mirrors
# the shape of MarketingStateOut so applying one is "wipe + insert" per entity
# list, plus an in-place update of the settings singleton. No new tables, no
# migration — the template id is just a filename slug.
# ---------------------------------------------------------------------------
def _templates_dir() -> Path:
    """Directory that holds the shipped industry-template JSON files."""
    return Path(__file__).resolve().parents[1] / "data" / "marketing_templates"


def _load_template_file(path: Path) -> dict | None:
    """Parse one template JSON file. Returns None and logs on any error so a
    single malformed file never crashes the templates gallery."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # broad: malformed JSON, FS issues, encoding bugs
        logger.warning("Skipping unreadable marketing template {}: {}", path.name, exc)
        return None


def list_templates() -> list[dict]:
    """Return metadata for every template in ``data/marketing_templates/``.

    Used by the editor's "Pick a template" gallery — only the small surface
    needed to render a card (id / name / description / preview_image), not the
    full JSON, so the gallery stays cheap to load.
    """
    out: list[dict] = []
    d = _templates_dir()
    if not d.exists():
        return out
    for path in sorted(d.glob("*.json")):
        data = _load_template_file(path)
        if data is None:
            continue
        out.append({
            "id": data.get("id") or path.stem,
            "name": data.get("name") or path.stem.replace("_", " ").title(),
            "description": data.get("description", ""),
            "preview_image": data.get("preview_image"),
        })
    return out


def get_template(template_id: str) -> dict | None:
    """Return the full JSON for one template, or None if it does not exist
    or is unparseable. ``template_id`` is the filename stem."""
    # Reject path-traversal attempts before touching the filesystem — a
    # ``..`` segment or absolute path could otherwise escape the templates dir.
    safe = template_id.strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        return None
    path = _templates_dir() / f"{safe}.json"
    if not path.exists() or not path.is_file():
        return None
    return _load_template_file(path)


def apply_template(
    db: Session,
    template_id: str,
    *,
    wipe_existing: bool = True,
) -> MarketingStateOut:
    """Apply a template to the current install.

    When ``wipe_existing`` is True (the default — matches "I just clicked a
    new template, start fresh"), every list-shaped entity is cleared before
    the template rows are inserted. When False, the template's rows are
    appended to whatever the user already has — useful for layering a smaller
    starter pack onto in-progress content.

    Settings are always updated in place (the row is a singleton). Uploads
    are never touched because templates ship without binary assets.
    """
    template = get_template(template_id)
    if template is None:
        raise ValidationFailed(f"Template '{template_id}' not found")

    # --- 1. Settings (singleton update, never wipe) ----------------------
    s = get_settings(db)
    for key, value in (template.get("settings") or {}).items():
        if hasattr(s, key) and value is not None:
            setattr(s, key, value)

    # --- 2. List-shaped entities ----------------------------------------
    # Tuple of (model, key in template JSON, extra processing if needed).
    list_entities = [
        (MarketingNavItem, "navigation"),
        (MarketingSection, "sections"),
        (MarketingService, "services"),
        (MarketingTestimonial, "testimonials"),
        (MarketingFAQ, "faqs"),
        (MarketingTeamMember, "team"),
        (MarketingSocialLink, "social_links"),
    ]
    for model, key in list_entities:
        if wipe_existing:
            db.query(model).delete()
            db.flush()
        for row in template.get(key) or []:
            cleaned = _drop_server_fields(row)
            db.add(model(**cleaned))

    # --- 3. Projects (have a unique slug — derive from title) -----------
    if wipe_existing:
        db.query(MarketingProject).delete()
        db.flush()
    for row in template.get("projects") or []:
        cleaned = _drop_server_fields(row)
        title = cleaned.get("title", "Untitled")
        cleaned["slug"] = unique_slug(db, MarketingProject, slugify(title))
        db.add(MarketingProject(**cleaned))

    # --- 4. Posts (have a unique slug — prefer template slug, else derive) -
    if wipe_existing:
        db.query(MarketingPost).delete()
        db.flush()
    for row in template.get("posts") or []:
        cleaned = _drop_server_fields(row)
        # Templates carry a slug for posts; fall back to slugifying the title
        # if a hand-written template forgot one.
        base = cleaned.pop("slug", None) or slugify(cleaned.get("title", "untitled"))
        cleaned["slug"] = unique_slug(db, MarketingPost, base)
        db.add(MarketingPost(**cleaned))

    db.commit()
    return get_full_state(db)


# Server-assigned columns that templates must never set. ``slug`` is dropped
# from the generic path because Project/Post handle slugs explicitly above.
_SERVER_FIELDS: frozenset[str] = frozenset({
    "id", "created_at", "updated_at", "image_id", "slug",
})


def _drop_server_fields(row: dict) -> dict:
    """Return a shallow copy of ``row`` with server-assigned fields removed."""
    return {k: v for k, v in row.items() if k not in _SERVER_FIELDS}


# ---------------------------------------------------------------------------
# SiteForge JSON export import (Phase 2)
#
# SiteForge Studio (the browser-only ancestor) persists everything under
# ``localStorage["siteforge.state.v1"]`` and exports the same shape as JSON via
# Settings → Data → Export. The shape is camelCase / nested and uses some
# SiteForge-only fields (activity log, launch checklist, meta) that we drop on
# import. The translation below converts the camelCase keys to the snake_case
# columns the EnterpriseCore marketing tables expect.
# ---------------------------------------------------------------------------
SITEFORGE_REQUIRED_KEYS: frozenset[str] = frozenset({
    "siteSettings", "themeSettings", "sections", "projects",
})

# Settings: SiteForge ``siteSettings`` keys → MarketingSettings columns.
_SITE_SETTINGS_MAP: dict[str, str] = {
    "name": "name",
    "tagline": "tagline",
    "description": "description",
    "logoText": "logo_text",
    "logoDot": "logo_dot",
    "baseUrl": "base_url",
    "seoTitle": "seo_title",
    "seoDescription": "seo_description",
}
# Theme: SiteForge ``themeSettings`` keys → MarketingSettings columns.
_THEME_SETTINGS_MAP: dict[str, str] = {
    "mode": "theme_mode",
    "primaryColor": "primary_color",
    "accentColor": "accent_color",
    "headingFont": "heading_font",
    "bodyFont": "body_font",
    "buttonStyle": "button_style",
    "density": "density",
    "radius": "radius",
}
# Contact: SiteForge ``contactInfo`` keys → MarketingSettings columns.
_CONTACT_INFO_MAP: dict[str, str] = {
    "email": "contact_email",
    "phone": "contact_phone",
    "address": "contact_address",
    "hours": "contact_hours",
}


def _coerce_settings_from_siteforge(payload: dict) -> dict:
    """Flatten SiteForge's nested siteSettings/themeSettings/contactInfo into
    the single MarketingSettings row shape (snake_case columns)."""
    out: dict = {}
    for src_key, dst_key in _SITE_SETTINGS_MAP.items():
        if src_key in (payload.get("siteSettings") or {}):
            out[dst_key] = payload["siteSettings"][src_key]
    for src_key, dst_key in _THEME_SETTINGS_MAP.items():
        if src_key in (payload.get("themeSettings") or {}):
            out[dst_key] = payload["themeSettings"][src_key]
    for src_key, dst_key in _CONTACT_INFO_MAP.items():
        if src_key in (payload.get("contactInfo") or {}):
            out[dst_key] = payload["contactInfo"][src_key]
    return out


def _coerce_section(row: dict) -> dict:
    """SiteForge sections carry a ``type``, eyebrow/title/body and a bag of
    type-specific extras. The extras live under MarketingSection.payload as
    JSON. We carry over what we can identify and stash the rest in payload."""
    known = {"id", "type", "enabled", "eyebrow", "title", "body", "order"}
    out = {
        "type": row.get("type", "hero"),
        "enabled": bool(row.get("enabled", True)),
        "eyebrow": row.get("eyebrow", "") or "",
        "title": row.get("title", "") or "",
        "body": row.get("body", "") or "",
        "order": int(row.get("order", 0) or 0),
    }
    payload = {k: v for k, v in row.items() if k not in known}
    if payload:
        out["payload"] = payload
    return out


def _coerce_nav(row: dict) -> dict:
    return {
        "label": (row.get("label") or "").strip() or "Untitled",
        "route": row.get("route") or "home",
        "enabled": bool(row.get("enabled", True)),
        "order": int(row.get("order", 0) or 0),
    }


def _coerce_project(row: dict) -> dict:
    return {
        "title": row.get("title") or "Untitled",
        "client": row.get("client", "") or "",
        "category": row.get("category", "") or "",
        "summary": row.get("summary", "") or "",
        "body": row.get("body", "") or "",
        "year": str(row.get("year", "") or ""),
        "tags": list(row.get("tags") or []),
        "featured": bool(row.get("featured", False)),
        # SiteForge stored ``url`` as external link; we map it to external_url.
        "external_url": row.get("url", "") or "",
        "order": int(row.get("order", 0) or 0),
    }


def _coerce_post(row: dict) -> dict:
    publish_date = row.get("publishDate") or row.get("publish_date")
    out: dict = {
        "title": row.get("title") or "Untitled",
        "excerpt": row.get("excerpt", "") or "",
        "body": row.get("body", "") or "",
        "author": row.get("author", "") or "",
        "category": row.get("category", "") or "",
        "tags": list(row.get("tags") or []),
        "status": row.get("status") or "draft",
        "seo_title": row.get("seoTitle", "") or "",
        "seo_description": row.get("seoDescription", "") or "",
    }
    parsed = _parse_publish_date(publish_date)
    if parsed is not None:
        out["publish_date"] = parsed
    if row.get("slug"):
        out["slug"] = row["slug"]
    return out


def _parse_publish_date(value) -> datetime | None:
    """SiteForge stores publishDate as ISO date / datetime strings. The
    destination column expects a Python ``datetime`` because SQLAlchemy's
    SQLite DateTime adapter refuses raw text."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    # Date-only form, common from SiteForge's <input type="date">.
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Could not parse SiteForge publishDate {!r}; dropping", text)
        return None


def _coerce_service(row: dict) -> dict:
    return {
        "icon": row.get("icon", "") or "",
        "title": row.get("title") or "Untitled",
        "summary": row.get("summary", "") or "",
        "details": row.get("details", "") or "",
        "price": row.get("price", "") or "",
        "featured": bool(row.get("featured", False)),
        "order": int(row.get("order", 0) or 0),
    }


def _coerce_testimonial(row: dict) -> dict:
    return {
        "quote": row.get("quote") or "",
        "author": row.get("author", "") or "",
        "role": row.get("role", "") or "",
        "order": int(row.get("order", 0) or 0),
    }


def _coerce_faq(row: dict) -> dict:
    # SiteForge uses {q, a}; the model uses question/answer.
    return {
        "question": row.get("question") or row.get("q") or "",
        "answer": row.get("answer") or row.get("a") or "",
        "order": int(row.get("order", 0) or 0),
    }


def _coerce_team_member(row: dict) -> dict:
    return {
        "name": row.get("name") or "Unnamed",
        "role": row.get("role", "") or "",
        "order": int(row.get("order", 0) or 0),
    }


def _coerce_social_link(row: dict) -> dict:
    return {
        "platform": row.get("platform") or "link",
        "label": row.get("label", "") or "",
        "url": row.get("url", "") or "",
        "order": int(row.get("order", 0) or 0),
    }


def apply_siteforge_export(
    db: Session,
    payload: dict,
    *,
    wipe_existing: bool = True,
) -> MarketingStateOut:
    """Import a SiteForge Studio JSON export into the EnterpriseCore install.

    Mirrors ``apply_template`` but the input is operator-supplied (so we
    validate the shape) and the field names are SiteForge's camelCase / nested
    layout, not the snake_case template format. SiteForge-only fields
    (``activity``, ``launchChecklist``, ``meta``) are silently dropped.
    """
    if not isinstance(payload, dict):
        raise ValidationFailed("SiteForge export must be a JSON object.")

    missing = SITEFORGE_REQUIRED_KEYS - set(payload.keys())
    if missing:
        raise ValidationFailed(
            "SiteForge export is missing required keys: "
            + ", ".join(sorted(missing))
        )

    # --- 1. Settings (singleton in-place update) -------------------------
    s = get_settings(db)
    for key, value in _coerce_settings_from_siteforge(payload).items():
        if value is None:
            continue
        setattr(s, key, value)

    # --- 2. List-shaped entities ----------------------------------------
    list_entities = [
        (MarketingNavItem, "navigation", _coerce_nav),
        (MarketingSection, "sections", _coerce_section),
        (MarketingService, "services", _coerce_service),
        (MarketingTestimonial, "testimonials", _coerce_testimonial),
        (MarketingFAQ, "faqs", _coerce_faq),
        (MarketingTeamMember, "team", _coerce_team_member),
        (MarketingSocialLink, "socialLinks", _coerce_social_link),
    ]
    for model, key, coerce in list_entities:
        if wipe_existing:
            db.query(model).delete()
            db.flush()
        for row in payload.get(key) or []:
            if not isinstance(row, dict):
                continue
            db.add(model(**coerce(row)))

    # --- 3. Projects (need a unique slug derived from title) -------------
    if wipe_existing:
        db.query(MarketingProject).delete()
        db.flush()
    for row in payload.get("projects") or []:
        if not isinstance(row, dict):
            continue
        cleaned = _coerce_project(row)
        cleaned["slug"] = unique_slug(db, MarketingProject, slugify(cleaned["title"]))
        db.add(MarketingProject(**cleaned))

    # --- 4. Posts (slug preferred from export, else derived) -------------
    if wipe_existing:
        db.query(MarketingPost).delete()
        db.flush()
    for row in payload.get("posts") or []:
        if not isinstance(row, dict):
            continue
        cleaned = _coerce_post(row)
        base = cleaned.pop("slug", None) or slugify(cleaned.get("title", "untitled"))
        cleaned["slug"] = unique_slug(db, MarketingPost, base)
        db.add(MarketingPost(**cleaned))

    db.commit()
    return get_full_state(db)
