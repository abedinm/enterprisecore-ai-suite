"""SQLAlchemy models for the Web Chat Widget module.

Three tables back the embeddable chat widget that lives on customer websites:

* ``Bot`` — owned by an EnterpriseCore user; carries the system prompt,
  language preset, AI provider/model, an optional BYO Fernet-encrypted API
  key, and per-bot rate-limit settings.
* ``Conversation`` — one row per (bot, visitor session). When the visitor
  hands over email/phone via ``contact_hint`` we resolve a ``Contact`` from
  the CRM module and link it here so dashboards can stitch chats to leads.
* ``ChatMessage`` — each user/assistant/system turn with usage stats so the
  bot owner can see exactly what the bot is costing them.

Ported from F:/LinguaBot but rewritten for EnterpriseCore conventions
(IdMixin/TimestampMixin ULID PKs, plan-gated, CRM-linked).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, Numeric,
                        String, Text, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Bot(IdMixin, TenantMixin, TimestampMixin, Base):
    """An embeddable chat bot owned by an EnterpriseCore user."""

    __tablename__ = "webchat_bots"

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    # auto / en / bn / hi / ur — when set, the bot replies in this language;
    # "auto" lets the language detector pick from the visitor's message.
    language_preset: Mapped[str] = mapped_column(
        String(16), default="auto", nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model: Mapped[str] = mapped_column(
        String(120), default="claude-haiku-4-5-20251001", nullable=False
    )
    provider: Mapped[str] = mapped_column(
        String(40), default="anthropic", nullable=False
    )
    # Public bots can be embedded on third-party websites; private bots refuse
    # /chat/{id} so the widget code can never address them. Default True so a
    # freshly-created bot is immediately useable.
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Fernet-encrypted BYO API key. Null → fall through to the server's
    # configured provider key in app.services.ai.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    rate_limit_per_min: Mapped[int] = mapped_column(
        Integer, default=20, nullable=False
    )
    # Denormalised counter so the dashboard can render "X messages today" /
    # "X messages all-time" without scanning every ChatMessage row.
    system_messages_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )


class Conversation(IdMixin, TenantMixin, Base):
    """One conversation per (bot, visitor session). Optionally linked to a CRM
    Contact once the visitor identifies themselves via email/phone."""

    __tablename__ = "webchat_conversations"

    bot_id: Mapped[str] = mapped_column(
        ForeignKey("webchat_bots.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    visitor_session_id: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True
    )
    visitor_locale_hint: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        nullable=False, index=True,
    )


class ChatMessage(IdMixin, TenantMixin, Base):
    """One message inside a Conversation."""

    __tablename__ = "webchat_messages"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("webchat_conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    language_detected: Mapped[str | None] = mapped_column(String(8))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
