"""Web Chat Widget — bots, conversations, messages.

Adds three new tables that back the embeddable chat widget. Idempotent: skips
any table that already exists so a fresh DB built by
``Base.metadata.create_all`` (which would have made the tables already) can
still be stamped clean.

Revision ID: 0008_webchat
Revises: 0007_user_mfa
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_webchat"
down_revision: str | None = "0007_user_mfa"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("webchat_bots"):
        op.create_table(
            "webchat_bots",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "owner_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("name", sa.String(length=180), nullable=False, index=True),
            sa.Column("description", sa.Text),
            sa.Column("language_preset", sa.String(length=16),
                      server_default="auto", nullable=False),
            sa.Column("system_prompt", sa.Text, server_default="", nullable=False),
            sa.Column("model", sa.String(length=120),
                      server_default="claude-haiku-4-5-20251001", nullable=False),
            sa.Column("provider", sa.String(length=40),
                      server_default="anthropic", nullable=False),
            sa.Column("is_public", sa.Boolean,
                      server_default=sa.text("1"), nullable=False),
            sa.Column("api_key_encrypted", sa.Text),
            sa.Column("rate_limit_per_min", sa.Integer,
                      server_default="20", nullable=False),
            sa.Column("system_messages_count", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("webchat_conversations"):
        op.create_table(
            "webchat_conversations",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "bot_id", sa.String(length=32),
                sa.ForeignKey("webchat_bots.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "contact_id", sa.String(length=32),
                sa.ForeignKey("contacts.id", ondelete="SET NULL"), index=True,
            ),
            sa.Column("visitor_session_id", sa.String(length=120),
                      nullable=False, index=True),
            sa.Column("visitor_locale_hint", sa.String(length=40)),
            sa.Column("started_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(),
                      nullable=False, index=True),
        )

    if not _has_table("webchat_messages"):
        op.create_table(
            "webchat_messages",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "conversation_id", sa.String(length=32),
                sa.ForeignKey("webchat_conversations.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("tokens_in", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("tokens_out", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("cost_usd", sa.Numeric(12, 6),
                      server_default="0", nullable=False),
            sa.Column("language_detected", sa.String(length=8)),
            sa.Column("latency_ms", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for tbl in ("webchat_messages", "webchat_conversations", "webchat_bots"):
        if _has_table(tbl):
            op.drop_table(tbl)
