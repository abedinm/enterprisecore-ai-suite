"""Web Chat Widget endpoints — bot CRUD, conversation viewing, public chat.

All routes here are gated by ``require_plan_feature("webchat")`` so the module
disappears entirely on plans that don't include it. Authenticated endpoints
additionally require the user own the bot they're touching; the public
``/chat/{bot_id}`` route is intentionally credential-free so the embeddable
widget can run on any third-party site.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_plan_feature
from app.core.exceptions import AppError, NotFoundError
from app.core.rate_limit import RateLimit
from app.db.session import get_db
from app.models.user import User
from app.models.webchat import Bot, ChatMessage, Conversation
from app.schemas.webchat import (
    BotCreate, BotOut, BotPublicOut, BotUpdate, ChatMessageOut, ConversationOut,
    ConversationWithMessagesOut, PublicChatIn, PublicChatOut,
)
from app.services import webchat as webchat_svc

router = APIRouter(dependencies=[Depends(require_plan_feature("webchat"))])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _bot_to_out(bot: Bot) -> BotOut:
    return BotOut(
        id=bot.id,
        owner_id=bot.owner_id,
        name=bot.name,
        description=bot.description,
        language_preset=bot.language_preset,
        system_prompt=bot.system_prompt or "",
        model=bot.model,
        provider=bot.provider,
        is_public=bot.is_public,
        has_byo_key=bool(bot.api_key_encrypted),
        rate_limit_per_min=bot.rate_limit_per_min,
        system_messages_count=bot.system_messages_count or 0,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
    )


def _owned_bot_or_404(db: Session, bot_id: str, owner_id: str) -> Bot:
    bot = db.get(Bot, bot_id)
    # Return 404 (not 403) for not-owned so we don't leak existence.
    if not bot or bot.owner_id != owner_id:
        raise NotFoundError("Bot not found")
    return bot


# ---------------------------------------------------------------------------
# Authenticated — bot CRUD
# ---------------------------------------------------------------------------
@router.post("/bots", response_model=BotOut, status_code=status.HTTP_201_CREATED)
def create_bot(
    payload: BotCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    bot = Bot(
        owner_id=current.id,
        name=payload.name.strip(),
        description=payload.description,
        language_preset=payload.language_preset,
        system_prompt=payload.system_prompt or "",
        model=payload.model,
        provider=payload.provider,
        is_public=payload.is_public,
        api_key_encrypted=webchat_svc.encrypt_bot_api_key(payload.api_key),
        rate_limit_per_min=payload.rate_limit_per_min,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return _bot_to_out(bot)


@router.get("/bots", response_model=list[BotOut])
def list_bots(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    rows = db.scalars(
        select(Bot)
        .where(Bot.owner_id == current.id)
        .order_by(Bot.updated_at.desc())
    ).all()
    return [_bot_to_out(b) for b in rows]


@router.get("/bots/{bot_id}", response_model=BotOut)
def get_bot(
    bot_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _bot_to_out(_owned_bot_or_404(db, bot_id, current.id))


@router.patch("/bots/{bot_id}", response_model=BotOut)
def update_bot(
    bot_id: str,
    payload: BotUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    bot = _owned_bot_or_404(db, bot_id, current.id)
    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        api_key = data.pop("api_key")
        # Empty string explicitly clears the key; None means "don't change".
        bot.api_key_encrypted = (
            webchat_svc.encrypt_bot_api_key(api_key) if api_key else None
        )
    for key, value in data.items():
        if value is not None:
            setattr(bot, key, value)
    db.commit()
    db.refresh(bot)
    return _bot_to_out(bot)


@router.delete("/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bot(
    bot_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    bot = _owned_bot_or_404(db, bot_id, current.id)
    db.delete(bot)
    db.commit()


# ---------------------------------------------------------------------------
# Authenticated — conversation viewing
# ---------------------------------------------------------------------------
@router.get("/bots/{bot_id}/conversations", response_model=list[ConversationOut])
def list_bot_conversations(
    bot_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _owned_bot_or_404(db, bot_id, current.id)
    return db.scalars(
        select(Conversation)
        .where(Conversation.bot_id == bot_id)
        .order_by(Conversation.last_message_at.desc())
        .limit(min(max(limit, 1), 500))
    ).all()


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationWithMessagesOut,
)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    convo = db.get(Conversation, conversation_id)
    if not convo:
        raise NotFoundError("Conversation not found")
    bot = db.get(Bot, convo.bot_id)
    if not bot or bot.owner_id != current.id:
        raise NotFoundError("Conversation not found")
    msgs = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return ConversationWithMessagesOut(
        id=convo.id,
        bot_id=convo.bot_id,
        contact_id=convo.contact_id,
        visitor_session_id=convo.visitor_session_id,
        visitor_locale_hint=convo.visitor_locale_hint,
        started_at=convo.started_at,
        last_message_at=convo.last_message_at,
        messages=[ChatMessageOut.model_validate(m) for m in msgs],
    )


# ---------------------------------------------------------------------------
# Public — embeddable widget chat
# ---------------------------------------------------------------------------
# A small global IP-based limiter sits at the route boundary so a single
# attacker can't bury us in 404s before we even look at the bot. The
# per-bot/per-session cap (using bot.rate_limit_per_min) is applied inside
# the handler once we've loaded the bot.
_PUBLIC_IP_LIMIT = RateLimit("120/minute", id="webchat-public-ip")


@router.get("/bots/public/{bot_id}", response_model=BotPublicOut)
def public_bot_metadata(
    bot_id: str,
    db: Session = Depends(get_db),
    _ip_throttle: None = Depends(_PUBLIC_IP_LIMIT),
):
    """Public bot metadata — what the embeddable widget needs to bootstrap.

    Returns 404 for private or missing bots (don't leak existence).
    """
    bot = db.get(Bot, bot_id)
    if not bot or not bot.is_public:
        raise NotFoundError("Bot not found")
    return BotPublicOut(
        id=bot.id,
        name=bot.name,
        language_preset=bot.language_preset,
        is_public=bot.is_public,
    )


@router.post("/chat/{bot_id}", response_model=PublicChatOut)
def public_chat(
    bot_id: str,
    payload: PublicChatIn,
    request: Request,
    db: Session = Depends(get_db),
    _ip_throttle: None = Depends(_PUBLIC_IP_LIMIT),
):
    bot = db.get(Bot, bot_id)
    # 404 (not 403) for private bots so we don't leak their existence.
    if not bot or not bot.is_public:
        raise NotFoundError("Bot not found")

    # Per-(bot, visitor_session) sliding-window cap using the bot's own
    # configured ceiling. ``RateLimit`` itself is IP-keyed; we use it here
    # only to get the same parse-and-window machinery, with a synthetic key
    # so two visitors can't share each other's quota.
    limit_id = f"webchat-bot-{bot.id}"
    count = max(1, bot.rate_limit_per_min)
    from app.core.rate_limit import _window  # internal accessor — see rate_limit.py
    allowed, retry = _window.hit(
        limit_id, payload.visitor_session_id, count, 60.0,
    )
    if not allowed:
        raise AppError(
            f"Too many requests for this chat session. Retry in {retry}s.",
            code="rate_limited", status_code=429,
        )

    user_msg, asst_msg, language = webchat_svc.process_public_message(
        db, bot, payload,
    )
    return PublicChatOut(
        reply=asst_msg.content,
        conversation_id=asst_msg.conversation_id,
        message_id=asst_msg.id,
        language_detected=language,
    )
