"""Pydantic v2 schemas for the Marketing Site Builder module.

A handful of conventions:

* Every list-shaped entity gets ``Create`` / ``Update`` / ``Out`` variants.
* The settings singleton is exposed as ``MarketingSettingsOut`` /
  ``MarketingSettingsUpdate`` (no ``Create`` — it's seeded once at first boot).
* ``MarketingStateOut`` bundles everything into a single payload so the editor
  and the public renderer can hydrate from one request.
* Section payloads are typed as ``dict[str, Any]`` because shape varies by
  section type; validation happens in the editor.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---------------------------------------------------------------------------
# Reusable types
# ---------------------------------------------------------------------------
SectionType = Literal["hero", "services", "projects", "testimonials", "about", "cta"]
PostStatus = Literal["draft", "published"]
ThemeMode = Literal["light", "dark"]
ButtonStyle = Literal["square", "rounded"]
Density = Literal["comfortable", "compact"]
NavRoute = Literal["home", "about", "services", "portfolio", "blog", "contact"]


# ---------------------------------------------------------------------------
# Settings (singleton)
# ---------------------------------------------------------------------------
class MarketingSettingsOut(ORMModel):
    key: str
    name: str
    tagline: str
    description: str
    logo_text: str
    logo_dot: bool
    base_url: str
    seo_title: str
    seo_description: str
    theme_mode: str
    primary_color: str
    accent_color: str
    heading_font: str
    body_font: str
    button_style: str
    density: str
    radius: int
    contact_email: str
    contact_phone: str
    contact_address: str
    contact_hours: str
    updated_at: datetime


class MarketingSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    tagline: str | None = Field(default=None, max_length=300)
    description: str | None = None
    logo_text: str | None = Field(default=None, max_length=180)
    logo_dot: bool | None = None
    base_url: str | None = Field(default=None, max_length=500)
    seo_title: str | None = Field(default=None, max_length=300)
    seo_description: str | None = None
    theme_mode: ThemeMode | None = None
    primary_color: str | None = Field(default=None, max_length=16)
    accent_color: str | None = Field(default=None, max_length=16)
    heading_font: str | None = Field(default=None, max_length=120)
    body_font: str | None = Field(default=None, max_length=120)
    button_style: ButtonStyle | None = None
    density: Density | None = None
    radius: int | None = Field(default=None, ge=0, le=64)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=60)
    contact_address: str | None = Field(default=None, max_length=500)
    contact_hours: str | None = Field(default=None, max_length=255)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
class NavItemIn(BaseModel):
    """One nav row — used in the bulk PUT /navigation payload."""

    id: str | None = None
    label: str = Field(min_length=1, max_length=120)
    route: NavRoute
    enabled: bool = True
    order: int = 0


class NavItemOut(ORMModel):
    id: str
    label: str
    route: str
    enabled: bool
    order: int


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
class SectionCreate(BaseModel):
    type: SectionType
    enabled: bool = True
    eyebrow: str = Field(default="", max_length=180)
    title: str = Field(default="", max_length=300)
    body: str = ""
    order: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)


class SectionUpdate(BaseModel):
    type: SectionType | None = None
    enabled: bool | None = None
    eyebrow: str | None = Field(default=None, max_length=180)
    title: str | None = Field(default=None, max_length=300)
    body: str | None = None
    order: int | None = None
    payload: dict[str, Any] | None = None


class SectionOut(ORMModel):
    id: str
    type: str
    enabled: bool
    eyebrow: str
    title: str
    body: str
    order: int
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    client: str = Field(default="", max_length=180)
    category: str = Field(default="", max_length=120)
    summary: str = ""
    body: str = ""
    year: str = Field(default="", max_length=16)
    tags: list[str] = Field(default_factory=list)
    featured: bool = False
    image_id: str | None = None
    external_url: str = Field(default="", max_length=500)
    order: int = 0


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    client: str | None = Field(default=None, max_length=180)
    category: str | None = Field(default=None, max_length=120)
    summary: str | None = None
    body: str | None = None
    year: str | None = Field(default=None, max_length=16)
    tags: list[str] | None = None
    featured: bool | None = None
    image_id: str | None = None
    external_url: str | None = Field(default=None, max_length=500)
    order: int | None = None


class ProjectOut(ORMModel):
    id: str
    title: str
    slug: str
    client: str
    category: str
    summary: str
    body: str
    year: str
    tags: list[str]
    featured: bool
    image_id: str | None
    external_url: str
    order: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------
class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = ""
    body: str = ""
    author: str = Field(default="", max_length=180)
    category: str = Field(default="", max_length=120)
    tags: list[str] = Field(default_factory=list)
    publish_date: datetime | None = None
    status: PostStatus = "draft"
    seo_title: str = Field(default="", max_length=300)
    seo_description: str = ""


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    excerpt: str | None = None
    body: str | None = None
    author: str | None = Field(default=None, max_length=180)
    category: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None
    publish_date: datetime | None = None
    status: PostStatus | None = None
    seo_title: str | None = Field(default=None, max_length=300)
    seo_description: str | None = None


class PostOut(ORMModel):
    id: str
    title: str
    slug: str
    excerpt: str
    body: str
    author: str
    category: str
    tags: list[str]
    publish_date: datetime | None
    status: str
    seo_title: str
    seo_description: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
class ServiceCreate(BaseModel):
    icon: str = Field(default="", max_length=60)
    title: str = Field(min_length=1, max_length=180)
    summary: str = ""
    details: str = ""
    price: str = Field(default="", max_length=120)
    featured: bool = False
    order: int = 0


class ServiceUpdate(BaseModel):
    icon: str | None = Field(default=None, max_length=60)
    title: str | None = Field(default=None, min_length=1, max_length=180)
    summary: str | None = None
    details: str | None = None
    price: str | None = Field(default=None, max_length=120)
    featured: bool | None = None
    order: int | None = None


class ServiceOut(ORMModel):
    id: str
    icon: str
    title: str
    summary: str
    details: str
    price: str
    featured: bool
    order: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Testimonials
# ---------------------------------------------------------------------------
class TestimonialCreate(BaseModel):
    quote: str = Field(min_length=1)
    author: str = Field(default="", max_length=180)
    role: str = Field(default="", max_length=180)
    order: int = 0


class TestimonialUpdate(BaseModel):
    quote: str | None = None
    author: str | None = Field(default=None, max_length=180)
    role: str | None = Field(default=None, max_length=180)
    order: int | None = None


class TestimonialOut(ORMModel):
    id: str
    quote: str
    author: str
    role: str
    order: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# FAQs
# ---------------------------------------------------------------------------
class FAQCreate(BaseModel):
    question: str = Field(min_length=1)
    answer: str = ""
    order: int = 0


class FAQUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    order: int | None = None


class FAQOut(ORMModel):
    id: str
    question: str
    answer: str
    order: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------
class TeamMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    role: str = Field(default="", max_length=180)
    image_id: str | None = None
    order: int = 0


class TeamMemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    role: str | None = Field(default=None, max_length=180)
    image_id: str | None = None
    order: int | None = None


class TeamMemberOut(ORMModel):
    id: str
    name: str
    role: str
    image_id: str | None
    order: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Social links
# ---------------------------------------------------------------------------
class SocialLinkCreate(BaseModel):
    platform: str = Field(min_length=1, max_length=60)
    label: str = Field(default="", max_length=180)
    url: str = Field(min_length=1, max_length=500)
    order: int = 0


class SocialLinkUpdate(BaseModel):
    platform: str | None = Field(default=None, min_length=1, max_length=60)
    label: str | None = Field(default=None, max_length=180)
    url: str | None = Field(default=None, min_length=1, max_length=500)
    order: int | None = None


class SocialLinkOut(ORMModel):
    id: str
    platform: str
    label: str
    url: str
    order: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Media library (uploads)
# ---------------------------------------------------------------------------
class MarketingUploadOut(ORMModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    uploaded_by_id: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Reorder / bulk
# ---------------------------------------------------------------------------
class ReorderEntry(BaseModel):
    id: str
    order: int


# ---------------------------------------------------------------------------
# Launch checklist
# ---------------------------------------------------------------------------
class LaunchChecklistItem(BaseModel):
    id: str
    label: str
    done: bool


# ---------------------------------------------------------------------------
# Combined state — used for editor hydration + public render
# ---------------------------------------------------------------------------
class MarketingStateOut(BaseModel):
    settings: MarketingSettingsOut
    navigation: list[NavItemOut]
    sections: list[SectionOut]
    projects: list[ProjectOut]
    posts: list[PostOut]
    services: list[ServiceOut]
    testimonials: list[TestimonialOut]
    faqs: list[FAQOut]
    team: list[TeamMemberOut]
    social_links: list[SocialLinkOut]
    uploads: list[MarketingUploadOut]
