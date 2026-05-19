"""SQLAlchemy models for the AI Brain module."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class AiConversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_conversations"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="anthropic", nullable=False)
    model: Mapped[str | None] = mapped_column(String(120))
    module: Mapped[str] = mapped_column(String(80), default="general", nullable=False)


class AiMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AiUsageRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage_records"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    feature: Mapped[str] = mapped_column(String(80), index=True, default="general", nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)


class Chatbot(IdMixin, TimestampMixin, Base):
    __tablename__ = "chatbots"

    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    welcome_message: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(40), default="anthropic", nullable=False)
    model: Mapped[str | None] = mapped_column(String(120))
    temperature: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.700"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    public_token: Mapped[str | None] = mapped_column(String(64), unique=True)


class ChatbotMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "chatbot_messages"

    chatbot_id: Mapped[str] = mapped_column(ForeignKey("chatbots.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
