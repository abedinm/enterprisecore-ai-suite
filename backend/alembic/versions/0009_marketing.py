"""Marketing Site Builder — settings singleton, nav, sections, projects,
posts, services, testimonials, faqs, team, social_links, uploads.

Adds eleven ``marketing_*`` tables backing the Studio editor and the public
rendered site. Idempotent: skips any table that already exists so a fresh DB
built by ``Base.metadata.create_all`` (which would have created the tables
already) can still be stamped clean.

Revision ID: 0009_marketing
Revises: 0008_webchat
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009_marketing"
down_revision: str | None = "0008_webchat"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("marketing_settings"):
        op.create_table(
            "marketing_settings",
            sa.Column("key", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=180), server_default="", nullable=False),
            sa.Column("tagline", sa.String(length=300), server_default="", nullable=False),
            sa.Column("description", sa.Text, server_default="", nullable=False),
            sa.Column("logo_text", sa.String(length=180), server_default="", nullable=False),
            sa.Column("logo_dot", sa.Boolean, server_default=sa.text("1"), nullable=False),
            sa.Column("base_url", sa.String(length=500), server_default="", nullable=False),
            sa.Column("seo_title", sa.String(length=300), server_default="", nullable=False),
            sa.Column("seo_description", sa.Text, server_default="", nullable=False),
            sa.Column("theme_mode", sa.String(length=16), server_default="light", nullable=False),
            sa.Column("primary_color", sa.String(length=16), server_default="#1f4fd1", nullable=False),
            sa.Column("accent_color", sa.String(length=16), server_default="#0f172a", nullable=False),
            sa.Column("heading_font", sa.String(length=120), server_default="Fraunces", nullable=False),
            sa.Column("body_font", sa.String(length=120), server_default="Inter", nullable=False),
            sa.Column("button_style", sa.String(length=16), server_default="square", nullable=False),
            sa.Column("density", sa.String(length=16), server_default="comfortable", nullable=False),
            sa.Column("radius", sa.Integer, server_default="8", nullable=False),
            sa.Column("contact_email", sa.String(length=255), server_default="", nullable=False),
            sa.Column("contact_phone", sa.String(length=60), server_default="", nullable=False),
            sa.Column("contact_address", sa.String(length=500), server_default="", nullable=False),
            sa.Column("contact_hours", sa.String(length=255), server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_uploads"):
        op.create_table(
            "marketing_uploads",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("filename", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("size_bytes", sa.Integer, server_default="0", nullable=False),
            sa.Column("storage_path", sa.String(length=500), nullable=False),
            sa.Column(
                "uploaded_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"), index=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_nav_items"):
        op.create_table(
            "marketing_nav_items",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("route", sa.String(length=60), nullable=False),
            sa.Column("enabled", sa.Boolean, server_default=sa.text("1"), nullable=False),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_sections"):
        op.create_table(
            "marketing_sections",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("type", sa.String(length=40), nullable=False, index=True),
            sa.Column("enabled", sa.Boolean, server_default=sa.text("1"), nullable=False),
            sa.Column("eyebrow", sa.String(length=180), server_default="", nullable=False),
            sa.Column("title", sa.String(length=300), server_default="", nullable=False),
            sa.Column("body", sa.Text, server_default="", nullable=False),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("payload", sa.JSON, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_projects"):
        op.create_table(
            "marketing_projects",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("title", sa.String(length=300), nullable=False, index=True),
            sa.Column("slug", sa.String(length=300), nullable=False, unique=True, index=True),
            sa.Column("client", sa.String(length=180), server_default="", nullable=False),
            sa.Column("category", sa.String(length=120), server_default="", nullable=False),
            sa.Column("summary", sa.Text, server_default="", nullable=False),
            sa.Column("body", sa.Text, server_default="", nullable=False),
            sa.Column("year", sa.String(length=16), server_default="", nullable=False),
            sa.Column("tags", sa.JSON, nullable=False),
            sa.Column("featured", sa.Boolean, server_default=sa.text("0"), nullable=False, index=True),
            sa.Column(
                "image_id", sa.String(length=32),
                sa.ForeignKey("marketing_uploads.id", ondelete="SET NULL"), index=True,
            ),
            sa.Column("external_url", sa.String(length=500), server_default="", nullable=False),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_posts"):
        op.create_table(
            "marketing_posts",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("title", sa.String(length=300), nullable=False, index=True),
            sa.Column("slug", sa.String(length=300), nullable=False, unique=True, index=True),
            sa.Column("excerpt", sa.Text, server_default="", nullable=False),
            sa.Column("body", sa.Text, server_default="", nullable=False),
            sa.Column("author", sa.String(length=180), server_default="", nullable=False),
            sa.Column("category", sa.String(length=120), server_default="", nullable=False),
            sa.Column("tags", sa.JSON, nullable=False),
            sa.Column("publish_date", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("status", sa.String(length=16),
                      server_default="draft", nullable=False, index=True),
            sa.Column("seo_title", sa.String(length=300), server_default="", nullable=False),
            sa.Column("seo_description", sa.Text, server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_services"):
        op.create_table(
            "marketing_services",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("icon", sa.String(length=60), server_default="", nullable=False),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column("summary", sa.Text, server_default="", nullable=False),
            sa.Column("details", sa.Text, server_default="", nullable=False),
            sa.Column("price", sa.String(length=120), server_default="", nullable=False),
            sa.Column("featured", sa.Boolean, server_default=sa.text("0"), nullable=False),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_testimonials"):
        op.create_table(
            "marketing_testimonials",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("quote", sa.Text, nullable=False),
            sa.Column("author", sa.String(length=180), server_default="", nullable=False),
            sa.Column("role", sa.String(length=180), server_default="", nullable=False),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_faqs"):
        op.create_table(
            "marketing_faqs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("question", sa.Text, nullable=False),
            sa.Column("answer", sa.Text, server_default="", nullable=False),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_team"):
        op.create_table(
            "marketing_team",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("role", sa.String(length=180), server_default="", nullable=False),
            sa.Column(
                "image_id", sa.String(length=32),
                sa.ForeignKey("marketing_uploads.id", ondelete="SET NULL"), index=True,
            ),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("marketing_social_links"):
        op.create_table(
            "marketing_social_links",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("platform", sa.String(length=60), nullable=False),
            sa.Column("label", sa.String(length=180), server_default="", nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("order", sa.Integer, server_default="0", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    # Reverse order: child tables (FKs into uploads) first.
    for tbl in (
        "marketing_social_links", "marketing_team", "marketing_faqs",
        "marketing_testimonials", "marketing_services", "marketing_posts",
        "marketing_projects", "marketing_sections", "marketing_nav_items",
        "marketing_uploads", "marketing_settings",
    ):
        if _has_table(tbl):
            op.drop_table(tbl)
