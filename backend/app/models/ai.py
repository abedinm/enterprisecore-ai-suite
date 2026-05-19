from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class AiConversation(IdMixin, TimestampMixin, Base):
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="ollama")
    module: Mapped[str] = mapped_column(String(80), default="general")


class AiMessage(IdMixin, TimestampMixin, Base):
    conversation_id: Mapped[str] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)


class AiUsageRecord(IdMixin, TimestampMixin, Base):
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)


class Chatbot(IdMixin, TimestampMixin, Base):
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    knowledge_sources: Mapped[str] = mapped_column(Text, default="[]")


class ChatbotMessage(IdMixin, TimestampMixin, Base):
    chatbot_id: Mapped[str] = mapped_column(ForeignKey("chatbots.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
