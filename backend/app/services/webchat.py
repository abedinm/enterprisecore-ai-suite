"""Web Chat Widget — language detection, conversation management, AI dispatch.

This module is the pure business logic that the HTTP endpoints in
``app/api/v1/endpoints/webchat.py`` call. Keeping it framework-free makes the
test suite small (no TestClient round-trips needed for service-level checks).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import decrypt_text, encrypt_text
from app.models.crm import CommunicationEntry, Contact
from app.models.webchat import Bot, ChatMessage, Conversation
from app.schemas.webchat import PublicChatIn
from app.services import ai as ai_svc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "bn", "hi", "ur")
LANGUAGE_NAMES = {
    "en": "English",
    "bn": "Bangla (Bengali)",
    "hi": "Hindi",
    "ur": "Urdu",
}
# How many prior messages (each side) to feed into the next AI call. Keeps
# prompts small and the per-call cost predictable.
HISTORY_TURNS = 8


# ---------------------------------------------------------------------------
# Language detection — Unicode-range heuristic for EN/BN/HI/UR
# ---------------------------------------------------------------------------
def detect_language(text: str) -> str:
    """Return one of 'en', 'bn', 'hi', 'ur' based on character script counts.

    Defaults to 'en' if no Latin/Bengali/Devanagari/Arabic characters are
    found (e.g. digits or punctuation only).
    """
    if not text:
        return "en"

    counts = {"en": 0, "bn": 0, "hi": 0, "ur": 0}
    for ch in text:
        o = ord(ch)
        if 0x0980 <= o <= 0x09FF:
            counts["bn"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["hi"] += 1
        elif (
            0x0600 <= o <= 0x06FF
            or 0xFB50 <= o <= 0xFDFF
            or 0xFE70 <= o <= 0xFEFF
        ):
            counts["ur"] += 1
        elif ch.isalpha() and o < 0x0250:
            counts["en"] += 1

    if all(v == 0 for v in counts.values()):
        return "en"
    return max(counts, key=lambda k: counts[k])


# ---------------------------------------------------------------------------
# BYO API key helpers
# ---------------------------------------------------------------------------
def encrypt_bot_api_key(plain: str | None) -> str | None:
    """Encrypt a BYO API key for storage. Empty / None → None."""
    if not plain:
        return None
    return encrypt_text(plain.strip())


def decrypt_bot_api_key(encrypted: str | None) -> str | None:
    """Decrypt a BYO API key. None / empty → None (caller falls back to server key)."""
    if not encrypted:
        return None
    try:
        return decrypt_text(encrypted)
    except Exception:
        # Bad ciphertext shouldn't break the chat — fall back to server key.
        return None


# ---------------------------------------------------------------------------
# Conversation lifecycle
# ---------------------------------------------------------------------------
def get_or_create_conversation(
    db: Session,
    *,
    bot_id: str,
    visitor_session_id: str,
    locale_hint: str | None = None,
) -> Conversation:
    """Look up the conversation for (bot, visitor) or create a new one."""
    convo = db.scalar(
        select(Conversation).where(
            Conversation.bot_id == bot_id,
            Conversation.visitor_session_id == visitor_session_id,
        )
    )
    if convo:
        return convo
    convo = Conversation(
        bot_id=bot_id,
        visitor_session_id=visitor_session_id,
        visitor_locale_hint=locale_hint,
    )
    db.add(convo)
    db.flush()
    try:
        from app.services.event_bus import publish_event

        publish_event(
            "webchat.conversation.created",
            payload={"conversation_id": convo.id, "bot_id": bot_id},
        )
    except Exception:  # pragma: no cover — never fail webchat on event bus
        pass
    return convo


def link_conversation_to_crm(
    db: Session,
    conversation: Conversation,
    contact_hint: dict,
    *,
    message_excerpt: str = "",
) -> Contact | None:
    """Resolve / create a CRM Contact and link it to this conversation.

    A ``CommunicationEntry`` row is also recorded so the CRM dashboard sees the
    chat alongside other touchpoints. Returns the linked Contact, or None when
    the hint had nothing actionable.
    """
    email = (contact_hint.get("email") or "").strip() or None
    phone = (contact_hint.get("phone") or "").strip() or None
    name = (contact_hint.get("name") or "").strip() or None

    if not email and not phone:
        return None

    filters = []
    if email:
        filters.append(Contact.email == email)
    if phone:
        filters.append(Contact.phone == phone)
    contact = db.scalar(select(Contact).where(or_(*filters))) if filters else None

    if not contact:
        contact = Contact(
            name=name or email or phone or "Web visitor",
            email=email,
            phone=phone,
        )
        db.add(contact)
        db.flush()
    else:
        # Fill in fields the hint provided that the existing contact lacks.
        if email and not contact.email:
            contact.email = email
        if phone and not contact.phone:
            contact.phone = phone

    was_unlinked = conversation.contact_id != contact.id
    conversation.contact_id = contact.id
    if was_unlinked:
        try:
            from app.services.event_bus import publish_event

            publish_event(
                "webchat.contact_linked",
                payload={
                    "conversation_id": conversation.id,
                    "contact_id": contact.id,
                    "bot_id": conversation.bot_id,
                },
            )
        except Exception:  # pragma: no cover
            pass

    db.add(
        CommunicationEntry(
            contact_id=contact.id,
            channel="webchat",
            subject="Web chat conversation",
            body=(message_excerpt or "")[:1000],
        )
    )
    db.flush()
    return contact


# ---------------------------------------------------------------------------
# AI dispatch
# ---------------------------------------------------------------------------
def _build_system_prompt(bot: Bot, language: str) -> str:
    base = (bot.system_prompt or "").strip() or (
        "You are a helpful customer-support assistant for the business that owns this widget. "
        "Answer concisely and stay on-topic."
    )
    if bot.language_preset == "auto":
        target = language
    else:
        target = bot.language_preset
    lang_name = LANGUAGE_NAMES.get(target, "English")
    return f"{base}\n\nIMPORTANT: Respond in {lang_name}."


def _provider_call(provider: str):
    """Pick the right ai_svc.call_* function for this provider."""
    return {
        "anthropic": ai_svc.call_anthropic,
        "openai": ai_svc.call_openai,
        "ollama": ai_svc.call_ollama,
    }.get(provider, ai_svc.call_anthropic)


def process_public_message(
    db: Session,
    bot: Bot,
    payload: PublicChatIn,
) -> tuple[ChatMessage, ChatMessage, str]:
    """Run one round-trip: detect language → load convo → save user msg → call
    the bot's configured AI provider → save assistant msg → optionally link to
    a CRM Contact. Returns (user_msg, assistant_msg, language_detected)."""
    language = detect_language(payload.message)

    convo = get_or_create_conversation(
        db,
        bot_id=bot.id,
        visitor_session_id=payload.visitor_session_id,
    )

    # Persist the user message before calling the model so we don't lose it
    # if the provider errors mid-call.
    user_msg = ChatMessage(
        conversation_id=convo.id,
        role="user",
        content=payload.message,
        language_detected=language,
    )
    db.add(user_msg)
    db.flush()

    # Build the message list: system prompt + last N history turns + this user msg.
    history = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == convo.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_TURNS * 2)
    ).all()
    history = list(reversed(history))  # chronological

    messages: list[ai_svc.AiMessage] = [
        ai_svc.AiMessage(role="system", content=_build_system_prompt(bot, language)),
    ]
    for m in history:
        if m.role in ("user", "assistant"):
            messages.append(ai_svc.AiMessage(role=m.role, content=m.content))

    api_key_override = decrypt_bot_api_key(bot.api_key_encrypted)
    call_fn = _provider_call(bot.provider)

    try:
        response = call_fn(
            messages,
            model=bot.model,
            max_tokens=600,
            temperature=0.7,
            api_key_override=api_key_override,
        )
    except AppError:
        # Commit the user message so it isn't lost, then re-raise so the
        # endpoint returns a meaningful 4xx/5xx.
        db.commit()
        raise

    assistant_msg = ChatMessage(
        conversation_id=convo.id,
        role="assistant",
        content=response.text or "(empty reply)",
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        cost_usd=response.cost_usd or Decimal("0"),
        language_detected=language,
        latency_ms=response.latency_ms,
    )
    db.add(assistant_msg)
    convo.last_message_at = datetime.now(timezone.utc)
    bot.system_messages_count = (bot.system_messages_count or 0) + 1
    db.flush()

    # Fire a realtime event so the bot owner's open ConversationsViewer
    # picks up the new turn without polling. Guarded — the event bus
    # must never break the chat flow.
    try:
        from app.services.event_bus import publish_event

        publish_event(
            "webchat.message.received",
            payload={
                "bot_id": bot.id,
                "conversation_id": convo.id,
                "language": language,
                "user_message_id": user_msg.id,
                "assistant_message_id": assistant_msg.id,
            },
            tenant_id=bot.tenant_id,
        )
    except Exception:  # pragma: no cover — defensive
        pass

    # Optionally link to a CRM contact + record a communication entry.
    if payload.contact_hint is not None:
        hint = payload.contact_hint.model_dump(exclude_none=True)
        if hint:
            link_conversation_to_crm(
                db, convo, hint, message_excerpt=payload.message,
            )

    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)
    return user_msg, assistant_msg, language
