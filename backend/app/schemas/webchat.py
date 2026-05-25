"""Pydantic v2 schemas for the Web Chat Widget module."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import ORMModel

LanguagePreset = Literal["auto", "en", "bn", "hi", "ur"]
Provider = Literal["anthropic", "openai", "ollama"]


# ---------------------------------------------------------------------------
# Bot CRUD
# ---------------------------------------------------------------------------
class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    language_preset: LanguagePreset = "auto"
    system_prompt: str = ""
    model: str = "claude-haiku-4-5-20251001"
    provider: Provider = "anthropic"
    is_public: bool = True
    api_key: str | None = Field(
        default=None,
        description="Plain BYO API key — stored Fernet-encrypted. Omit to use server key.",
    )
    rate_limit_per_min: int = Field(default=20, ge=1, le=600)


class BotUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    language_preset: LanguagePreset | None = None
    system_prompt: str | None = None
    model: str | None = None
    provider: Provider | None = None
    is_public: bool | None = None
    api_key: str | None = Field(
        default=None,
        description="Replace the BYO API key. Empty string clears it.",
    )
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=600)


class BotOut(ORMModel):
    id: str
    owner_id: str
    name: str
    description: str | None
    language_preset: str
    system_prompt: str
    model: str
    provider: str
    is_public: bool
    has_byo_key: bool
    rate_limit_per_min: int
    system_messages_count: int
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def embed_snippet(self) -> str:
        """The drop-in ``<script>`` snippet a customer pastes into their site
        to load this bot's widget. The widget.js asset is served at the root
        path so it's a stable, short URL customers can paste into any site."""
        return (
            f'<script src="/widget.js" '
            f'data-bot-id="{self.id}" defer></script>'
        )


# ---------------------------------------------------------------------------
# Public bot metadata (consumed by the embeddable widget on init)
# ---------------------------------------------------------------------------
class BotPublicOut(BaseModel):
    """Public-safe view of a Bot — what the embeddable widget sees on boot.

    Strictly excludes anything that could leak the operator's config:
    no owner_id, no system_prompt, no provider/model, no API key state,
    no usage counters.
    """
    id: str
    name: str
    language_preset: str
    is_public: bool


# ---------------------------------------------------------------------------
# Conversations and messages
# ---------------------------------------------------------------------------
class ChatMessageOut(ORMModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    language_detected: str | None
    latency_ms: int
    created_at: datetime


class ConversationOut(ORMModel):
    id: str
    bot_id: str
    contact_id: str | None
    visitor_session_id: str
    visitor_locale_hint: str | None
    started_at: datetime
    last_message_at: datetime


class ConversationWithMessagesOut(ConversationOut):
    messages: list[ChatMessageOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public widget I/O (no auth)
# ---------------------------------------------------------------------------
class ContactHint(BaseModel):
    email: str | None = None
    phone: str | None = None
    name: str | None = None


class PublicChatIn(BaseModel):
    visitor_session_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=10_000)
    contact_hint: ContactHint | None = None


class PublicChatOut(BaseModel):
    reply: str
    conversation_id: str
    message_id: str
    language_detected: str
