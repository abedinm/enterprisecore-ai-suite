"""SQLAlchemy models for the Marketing Site Builder.

Ported from F:/CodexProjects/siteforge-studio. The browser-only SiteForge app
keeps everything in localStorage; here we shape the same conceptual data into
discrete, plan-gated SQLAlchemy tables (``marketing_*``) so the editor and the
rendered public site share a single source of truth.

Singleton design notes
~~~~~~~~~~~~~~~~~~~~~~
``MarketingSettings`` collapses SiteForge's ``siteSettings``, ``themeSettings``
and ``contactInfo`` into one wide row identified by a fixed primary key
(``key="default"``) so the editor never juggles three singletons. Section
shapes vary by type (hero, services, projects, ...), so we store the
type-specific extras as JSON in ``payload`` while keeping the fields used for
querying (``type``, ``enabled``, ``order``, eyebrow/title/body) as proper
columns.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


# ---------------------------------------------------------------------------
# Singleton — site settings, theme, contact info
# ---------------------------------------------------------------------------
class MarketingSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """Site identity + theme + contact info. One row per tenant.

    Previously this was a single-row table keyed by ``key="default"`` because
    the suite was single-tenant. In the multi-tenant world each tenant owns
    its own settings row, so the row identity is now the standard ULID id
    plus a unique constraint on ``(tenant_id, key)``. The ``key`` column is
    kept (defaulting to ``"default"``) to leave the door open for per-tenant
    multi-site setups (e.g. ``"staging"`` / ``"main"``) without a schema
    change.
    """

    __tablename__ = "marketing_settings"

    key: Mapped[str] = mapped_column(String(32), default="default", nullable=False)

    # --- siteSettings ----------------------------------------------------
    name: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    tagline: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    logo_text: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    logo_dot: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    seo_title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    seo_description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # --- themeSettings ---------------------------------------------------
    # mode: "light" | "dark"
    theme_mode: Mapped[str] = mapped_column(String(16), default="light", nullable=False)
    primary_color: Mapped[str] = mapped_column(String(16), default="#1f4fd1", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(16), default="#0f172a", nullable=False)
    heading_font: Mapped[str] = mapped_column(String(120), default="Fraunces", nullable=False)
    body_font: Mapped[str] = mapped_column(String(120), default="Inter", nullable=False)
    # button_style: "square" | "rounded"
    button_style: Mapped[str] = mapped_column(String(16), default="square", nullable=False)
    # density: "comfortable" | "compact"
    density: Mapped[str] = mapped_column(String(16), default="comfortable", nullable=False)
    radius: Mapped[int] = mapped_column(Integer, default=8, nullable=False)

    # --- contactInfo -----------------------------------------------------
    contact_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    contact_address: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    contact_hours: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # One settings row per (tenant, key). Today ``key`` is always "default"
    # but the column lets a tenant add a "staging" site row later without a
    # schema change.
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_marketing_settings_tenant_key"),
    )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
class MarketingNavItem(IdMixin, TenantMixin, TimestampMixin, Base):
    """A single nav link in the public site header."""

    __tablename__ = "marketing_nav_items"

    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # ``route`` is one of: home | about | services | portfolio | blog | contact
    route: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Sections (hero, services list, projects list, testimonials, about, cta...)
# ---------------------------------------------------------------------------
class MarketingSection(IdMixin, TenantMixin, TimestampMixin, Base):
    """One section on the home page. Type-specific extras live in ``payload``.

    Common fields (eyebrow/title/body) are top-level columns because the editor
    and renderer both care about them in every type. ``payload`` (JSON) holds
    the type-specific extras — hero stats, hero CTAs, projects show_limit,
    etc. — so we don't have to add a new column every time a new section type
    is added.
    """

    __tablename__ = "marketing_sections"

    # type: hero | services | projects | testimonials | about | cta
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    eyebrow: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


# ---------------------------------------------------------------------------
# Portfolio projects
# ---------------------------------------------------------------------------
class MarketingProject(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "marketing_projects"

    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    # Slug for /site/portfolio/<slug> — unique within a tenant; two tenants
    # can both have a /portfolio/cafe-rebrand without colliding.
    slug: Mapped[str] = mapped_column(
        String(300), nullable=False, index=True
    )
    client: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    year: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    image_id: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_uploads.id", ondelete="SET NULL"), index=True
    )
    external_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)

    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_marketing_projects_tenant_slug"),)


# ---------------------------------------------------------------------------
# Blog posts
# ---------------------------------------------------------------------------
class MarketingPost(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "marketing_posts"

    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(
        String(300), nullable=False, index=True
    )
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    publish_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # status: draft | published
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False, index=True
    )
    seo_title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    seo_description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_marketing_posts_tenant_slug"),)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
class MarketingService(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "marketing_services"

    icon: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Testimonials
# ---------------------------------------------------------------------------
class MarketingTestimonial(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "marketing_testimonials"

    quote: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)


# ---------------------------------------------------------------------------
# FAQs
# ---------------------------------------------------------------------------
class MarketingFAQ(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "marketing_faqs"

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Team members
# ---------------------------------------------------------------------------
class MarketingTeamMember(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "marketing_team"

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    role: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    image_id: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_uploads.id", ondelete="SET NULL"), index=True
    )
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Social links
# ---------------------------------------------------------------------------
class MarketingSocialLink(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "marketing_social_links"

    platform: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Media library (uploads)
# ---------------------------------------------------------------------------
class MarketingUpload(IdMixin, TenantMixin, Base):
    """A single image in the marketing media library.

    Projects and team members reference uploads by id. Files live under
    ``storage/uploads/marketing/<yyyy-mm>/<id>.<ext>``. ``storage_path`` is
    kept relative to the backend ``storage/`` root so the install can be
    relocated without rewriting database rows.
    """

    __tablename__ = "marketing_uploads"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
