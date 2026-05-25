"""Unified AI service — Anthropic, OpenAI, and Ollama with cost/usage tracking.

Supports per-call ``api_key_override`` so the desktop client can bring its own key
(decrypted from Electron's safeStorage) without persisting it on the server.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.metrics import record_ai_call
from app.models.ai import AiUsageRecord

# Per-token USD prices (rough public defaults)
DEFAULT_PRICING = {
    "claude-haiku-4-5-20251001": (Decimal("0.0000008"), Decimal("0.000004")),
    "claude-sonnet-4-6": (Decimal("0.000003"), Decimal("0.000015")),
    "claude-opus-4-7": (Decimal("0.000015"), Decimal("0.000075")),
    "gpt-4o-mini": (Decimal("0.00000015"), Decimal("0.0000006")),
    "gpt-4o": (Decimal("0.0000025"), Decimal("0.00001")),
    "gpt-4-turbo": (Decimal("0.00001"), Decimal("0.00003")),
}

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.1",
}


@dataclass
class AiResponse:
    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal = Decimal("0")
    latency_ms: int = 0
    raw: dict | None = None


@dataclass
class AiMessage:
    role: str  # system|user|assistant
    content: str


def _cost(model: str, tin: int, tout: int) -> Decimal:
    rate = DEFAULT_PRICING.get(model, (Decimal("0"), Decimal("0")))
    return (rate[0] * Decimal(tin)) + (rate[1] * Decimal(tout))


def _record_usage(db: Session | None, *, user_id: str | None, provider: str, model: str,
                  feature: str, tin: int, tout: int, cost: Decimal, latency_ms: int,
                  success: bool = True) -> None:
    # Emit Prometheus metrics for EVERY call, even when there's no DB session
    # (test paths, BYO-key callers without an AiUsageRecord). Metrics are
    # cheap and they're the canonical operational signal.
    try:
        record_ai_call(
            provider=provider,
            model=model,
            feature=feature,
            success=success,
            tokens_in=tin or 0,
            tokens_out=tout or 0,
            cost_usd=float(cost) if cost is not None else 0.0,
            latency_seconds=(latency_ms or 0) / 1000.0,
        )
    except Exception as e:  # pragma: no cover - metrics must not break the app
        logger.warning("Failed to emit AI metrics: {}", e)

    if db is None:
        return
    try:
        db.add(AiUsageRecord(
            user_id=user_id, provider=provider, model=model, feature=feature,
            tokens_in=tin, tokens_out=tout, cost_usd=cost, latency_ms=latency_ms,
            success=success, occurred_at=datetime.now(timezone.utc),
        ))
        db.commit()
    except Exception as e:  # pragma: no cover
        logger.warning("Failed to record AI usage: {}", e)

    # Tenant-level metered-usage roll-up. Ollama (provider=="ollama") records
    # cost 0 so it's already exempt via the cost > 0 check inside
    # ``increment_ai_paid_usage``. Wrapped in its own try so a metering
    # failure can never break an AI call.
    try:
        from app.core.tenant_context import get_current_tenant_id
        from app.services.stripe_service import increment_ai_paid_usage

        tid = get_current_tenant_id()
        if tid and cost and success:
            increment_ai_paid_usage(db, tid, cost)
    except Exception as e:  # pragma: no cover
        logger.warning("Failed to increment tenant AI meter: {}", e)


def available_providers() -> dict[str, bool]:
    """Server-side configured providers. Clients can still call any provider by
    supplying ``api_key_override`` (their own BYO key)."""
    return {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "ollama": True,
    }


def _format_messages_for_claude(messages: list[AiMessage]) -> tuple[str, list[dict]]:
    system_parts = [m.content for m in messages if m.role == "system"]
    user_parts = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    if not user_parts:
        user_parts = [{"role": "user", "content": ""}]
    return "\n\n".join(system_parts), user_parts


def call_anthropic(messages: list[AiMessage], *, model: str | None = None,
                   max_tokens: int = 1024, temperature: float = 0.7,
                   api_key_override: str | None = None) -> AiResponse:
    key = api_key_override or settings.anthropic_api_key
    if not key:
        raise AppError("Anthropic API key not configured", code="ai_provider_not_configured")
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    system, conv = _format_messages_for_claude(messages)
    m = model or DEFAULT_MODELS["anthropic"]
    started = time.time()
    response = client.messages.create(
        model=m,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system or "You are a helpful assistant.",
        messages=conv,
    )
    latency_ms = int((time.time() - started) * 1000)
    text = "".join(getattr(block, "text", "") for block in response.content)
    tin = response.usage.input_tokens
    tout = response.usage.output_tokens
    return AiResponse(
        text=text, provider="anthropic", model=m,
        tokens_in=tin, tokens_out=tout, cost_usd=_cost(m, tin, tout),
        latency_ms=latency_ms, raw=None,
    )


def call_openai(messages: list[AiMessage], *, model: str | None = None,
                max_tokens: int = 1024, temperature: float = 0.7,
                api_key_override: str | None = None) -> AiResponse:
    key = api_key_override or settings.openai_api_key
    if not key:
        raise AppError("OpenAI API key not configured", code="ai_provider_not_configured")
    from openai import OpenAI

    client = OpenAI(api_key=key)
    m = model or DEFAULT_MODELS["openai"]
    conv = [{"role": x.role, "content": x.content} for x in messages]
    started = time.time()
    resp = client.chat.completions.create(
        model=m, messages=conv, max_tokens=max_tokens, temperature=temperature,
    )
    latency_ms = int((time.time() - started) * 1000)
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    tin = usage.prompt_tokens if usage else 0
    tout = usage.completion_tokens if usage else 0
    return AiResponse(
        text=text, provider="openai", model=m,
        tokens_in=tin, tokens_out=tout, cost_usd=_cost(m, tin, tout),
        latency_ms=latency_ms,
    )


def call_ollama(messages: list[AiMessage], *, model: str | None = None,
                max_tokens: int = 1024, temperature: float = 0.7,
                api_key_override: str | None = None) -> AiResponse:
    import httpx

    m = model or DEFAULT_MODELS["ollama"]
    conv = [{"role": x.role, "content": x.content} for x in messages]
    started = time.time()
    try:
        r = httpx.post(
            f"{settings.ollama_host}/api/chat",
            json={"model": m, "messages": conv, "stream": False,
                  "options": {"num_predict": max_tokens, "temperature": temperature}},
            timeout=120.0,
        )
        r.raise_for_status()
    except Exception as e:
        raise AppError(f"Ollama call failed: {e}", code="ai_provider_unavailable", status_code=503) from e
    latency_ms = int((time.time() - started) * 1000)
    body = r.json()
    text = body.get("message", {}).get("content", "")
    return AiResponse(
        text=text, provider="ollama", model=m,
        tokens_in=body.get("prompt_eval_count", 0),
        tokens_out=body.get("eval_count", 0),
        cost_usd=Decimal("0"),
        latency_ms=latency_ms,
    )


def user_daily_spend_usd(db: Session, user_id: str) -> Decimal:
    """Sum of cost_usd from this user's AI calls in the last 24h. Used by the
    cost-limit guard. Ollama records cost 0, so they don't count against quota."""
    from sqlalchemy import func, select as _sel
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    total = db.scalar(
        _sel(func.coalesce(func.sum(AiUsageRecord.cost_usd), 0))
        .where(AiUsageRecord.user_id == user_id, AiUsageRecord.occurred_at >= since)
    )
    return Decimal(total or 0)


def _check_spending_limit(db: Session | None, user_id: str | None, chosen: str) -> None:
    """Raise AppError(429) when the user's last-24h spend on PAID providers
    has reached settings.ai_daily_usd_limit_per_user. Ollama is exempt."""
    if db is None or user_id is None:
        return  # no DB → no tracking → no limit (test paths typically)
    limit = settings.ai_daily_usd_limit_per_user
    if limit <= 0 or chosen == "ollama":
        return
    spent = user_daily_spend_usd(db, user_id)
    if spent >= Decimal(str(limit)):
        raise AppError(
            f"Daily AI spending limit reached (${spent:.4f} of ${limit:.2f}). "
            f"Reset rolls over 24h after the first charge. "
            f"Switch provider to ollama for free local inference, or raise "
            f"AI_DAILY_USD_LIMIT_PER_USER.",
            code="ai_spend_limit",
            status_code=429,
        )


def call(messages: list[AiMessage], *, provider: str | None = None, model: str | None = None,
         max_tokens: int = 1024, temperature: float = 0.7,
         feature: str = "general", db: Session | None = None,
         user_id: str | None = None,
         api_key_override: str | None = None) -> AiResponse:
    """Dispatch to the requested provider with auto-fallback to Ollama on failure."""
    chosen = provider or settings.ai_default_provider
    available = available_providers()
    if not api_key_override and not available.get(chosen):
        for fb in ("anthropic", "openai", "ollama"):
            if available.get(fb):
                chosen = fb
                break
    # Per-user spend cap (free, local Ollama is exempt). Check before the call
    # so we don't pay for a request and then refuse to deliver it.
    _check_spending_limit(db, user_id, chosen)
    try:
        if chosen == "anthropic":
            result = call_anthropic(messages, model=model, max_tokens=max_tokens,
                                    temperature=temperature, api_key_override=api_key_override)
        elif chosen == "openai":
            result = call_openai(messages, model=model, max_tokens=max_tokens,
                                 temperature=temperature, api_key_override=api_key_override)
        else:
            result = call_ollama(messages, model=model, max_tokens=max_tokens,
                                 temperature=temperature)
    except AppError as e:
        if chosen != "ollama":
            logger.warning("AI provider {} failed ({}); falling back to Ollama", chosen, e)
            try:
                result = call_ollama(messages, model=model, max_tokens=max_tokens,
                                     temperature=temperature)
            except AppError:
                _record_usage(db, user_id=user_id, provider=chosen, model=model or "?",
                              feature=feature, tin=0, tout=0, cost=Decimal("0"),
                              latency_ms=0, success=False)
                raise e from None
        else:
            _record_usage(db, user_id=user_id, provider=chosen, model=model or "?",
                          feature=feature, tin=0, tout=0, cost=Decimal("0"),
                          latency_ms=0, success=False)
            raise
    _record_usage(db, user_id=user_id, provider=result.provider, model=result.model,
                  feature=feature, tin=result.tokens_in, tout=result.tokens_out,
                  cost=result.cost_usd, latency_ms=result.latency_ms, success=True)
    return result


# ---- Specialised wrappers ----------------------------------------------
def smart_text(prompt: str, *, system: str | None = None, feature: str = "general",
               provider: str | None = None, db: Session | None = None,
               user_id: str | None = None, max_tokens: int = 800,
               api_key_override: str | None = None) -> str:
    msgs = []
    if system:
        msgs.append(AiMessage(role="system", content=system))
    msgs.append(AiMessage(role="user", content=prompt))
    return call(msgs, provider=provider, max_tokens=max_tokens, feature=feature,
                db=db, user_id=user_id, api_key_override=api_key_override).text


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.lstrip("`")
        if "\n" in t:
            t = t.split("\n", 1)[1]
        if t.endswith("```"):
            t = t[:-3].rstrip()
    return t


def smart_json(prompt: str, *, system: str | None = None, feature: str = "general",
               provider: str | None = None, db: Session | None = None,
               user_id: str | None = None, max_tokens: int = 800,
               api_key_override: str | None = None) -> dict:
    raw = smart_text(prompt, system=system, feature=feature, provider=provider,
                     db=db, user_id=user_id, max_tokens=max_tokens,
                     api_key_override=api_key_override)
    cleaned = _strip_json_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try locating a JSON object in free text
        for start, end in (("{", "}"), ("[", "]")):
            i = cleaned.find(start)
            j = cleaned.rfind(end)
            if 0 <= i < j:
                try:
                    return json.loads(cleaned[i:j + 1])
                except json.JSONDecodeError:
                    continue
        return {"_raw": raw}


def analyze_sentiment(text: str, *, db: Session | None = None,
                     user_id: str | None = None) -> dict:
    prompt = (
        f"Classify the sentiment of this text. Reply with strict JSON only — no markdown — "
        f'with shape {{"label": "positive"|"neutral"|"negative", "score": 0.0..1.0, "summary": "<one short sentence>"}}.\n\n'
        f"TEXT:\n{text}"
    )
    data = smart_json(prompt, feature="sentiment", db=db, user_id=user_id, max_tokens=200,
                     system="You are a precise sentiment classifier. Output strict JSON.")
    if "_raw" in data:
        low = text.lower()
        if any(w in low for w in ("great", "love", "excellent", "amazing", "perfect")):
            return {"label": "positive", "score": 0.8, "summary": "(heuristic)"}
        if any(w in low for w in ("bad", "terrible", "awful", "hate", "broken")):
            return {"label": "negative", "score": 0.8, "summary": "(heuristic)"}
        return {"label": "neutral", "score": 0.5, "summary": "(heuristic)"}
    return {
        "label": data.get("label", "neutral"),
        "score": float(data.get("score", 0.5)),
        "summary": data.get("summary", ""),
    }


def summarise_meeting(transcript: str, *, db: Session | None = None,
                     user_id: str | None = None) -> dict:
    prompt = (
        "Summarise this meeting transcript. Respond with strict JSON only with this shape:\n"
        '{"summary": "<3-5 sentence overview>", "key_decisions": ["..."], "action_items": [{"owner": "...", "task": "...", "due": "..."}]}\n\n'
        f"TRANSCRIPT:\n{transcript}"
    )
    data = smart_json(prompt, feature="meeting_summary", db=db, user_id=user_id,
                     max_tokens=1200, system="You write concise, structured meeting summaries.")
    if "_raw" in data:
        return {"summary": data["_raw"], "key_decisions": [], "action_items": []}
    return data


def explain_regex(pattern: str, *, db: Session | None = None, user_id: str | None = None,
                 api_key_override: str | None = None, provider: str | None = None) -> str:
    return smart_text(
        f"Explain this regular expression in plain English, step by step:\n\n{pattern}",
        feature="regex_explain", db=db, user_id=user_id, max_tokens=400,
        system="You teach regex precisely and concisely.",
        api_key_override=api_key_override, provider=provider,
    )


# ---------------------------------------------------------------------------
# Streaming variants
# ---------------------------------------------------------------------------
def _stream_anthropic(messages: list[AiMessage], *, model: str | None,
                      max_tokens: int, temperature: float,
                      api_key_override: str | None = None):
    key = api_key_override or settings.anthropic_api_key
    if not key:
        raise AppError("Anthropic API key not configured",
                       code="ai_provider_not_configured")
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    system, conv = _format_messages_for_claude(messages)
    m = model or DEFAULT_MODELS["anthropic"]
    started = time.time()
    tokens_in = 0
    tokens_out = 0
    full_text_parts: list[str] = []
    with client.messages.stream(
        model=m, max_tokens=max_tokens, temperature=temperature,
        system=system or "You are a helpful assistant.", messages=conv,
    ) as stream:
        for delta in stream.text_stream:
            if delta:
                full_text_parts.append(delta)
                yield "token", {"text": delta}
        msg = stream.get_final_message()
        tokens_in = msg.usage.input_tokens
        tokens_out = msg.usage.output_tokens
    latency_ms = int((time.time() - started) * 1000)
    yield "usage", {
        "provider": "anthropic", "model": m,
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost_usd": str(_cost(m, tokens_in, tokens_out)),
        "latency_ms": latency_ms,
        "text": "".join(full_text_parts),
    }


def _stream_openai(messages: list[AiMessage], *, model: str | None,
                   max_tokens: int, temperature: float,
                   api_key_override: str | None = None):
    key = api_key_override or settings.openai_api_key
    if not key:
        raise AppError("OpenAI API key not configured", code="ai_provider_not_configured")
    from openai import OpenAI

    client = OpenAI(api_key=key)
    m = model or DEFAULT_MODELS["openai"]
    conv = [{"role": x.role, "content": x.content} for x in messages]
    started = time.time()
    full_text_parts: list[str] = []
    tokens_in = 0
    tokens_out = 0
    response = client.chat.completions.create(
        model=m, messages=conv, max_tokens=max_tokens, temperature=temperature,
        stream=True, stream_options={"include_usage": True},
    )
    for chunk in response:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_text_parts.append(delta.content)
                yield "token", {"text": delta.content}
        if chunk.usage:
            tokens_in = chunk.usage.prompt_tokens
            tokens_out = chunk.usage.completion_tokens
    latency_ms = int((time.time() - started) * 1000)
    yield "usage", {
        "provider": "openai", "model": m,
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost_usd": str(_cost(m, tokens_in, tokens_out)),
        "latency_ms": latency_ms,
        "text": "".join(full_text_parts),
    }


def _stream_ollama(messages: list[AiMessage], *, model: str | None,
                   max_tokens: int, temperature: float):
    import httpx

    m = model or DEFAULT_MODELS["ollama"]
    conv = [{"role": x.role, "content": x.content} for x in messages]
    started = time.time()
    tokens_in = 0
    tokens_out = 0
    full_text_parts: list[str] = []
    try:
        with httpx.Client(timeout=None) as client:
            with client.stream(
                "POST", f"{settings.ollama_host}/api/chat",
                json={
                    "model": m, "messages": conv, "stream": True,
                    "options": {"num_predict": max_tokens, "temperature": temperature},
                },
            ) as r:
                if r.status_code >= 400:
                    raise AppError(
                        f"Ollama HTTP {r.status_code}",
                        code="ai_provider_unavailable", status_code=503,
                    )
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = (ev.get("message") or {}).get("content", "")
                    if delta:
                        full_text_parts.append(delta)
                        yield "token", {"text": delta}
                    if ev.get("done"):
                        tokens_in = int(ev.get("prompt_eval_count") or 0)
                        tokens_out = int(ev.get("eval_count") or 0)
                        break
    except httpx.HTTPError as e:
        raise AppError(f"Ollama call failed: {e}",
                       code="ai_provider_unavailable", status_code=503) from e

    latency_ms = int((time.time() - started) * 1000)
    yield "usage", {
        "provider": "ollama", "model": m,
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost_usd": "0",
        "latency_ms": latency_ms,
        "text": "".join(full_text_parts),
    }


def stream_call(
    *, messages: list[AiMessage], provider: str | None = None,
    model: str | None = None, max_tokens: int = 1024, temperature: float = 0.7,
    feature: str = "general", db: Session | None = None,
    user_id: str | None = None, api_key_override: str | None = None,
):
    """Streaming counterpart of ``call``. Yields tuples of
    ``(event_type, payload)`` where event_type is one of ``token`` /
    ``usage`` / ``error``. Records AiUsageRecord at the end (success or fail).
    """
    chosen = provider or settings.ai_default_provider
    available = available_providers()
    if not api_key_override and not available.get(chosen):
        for fb in ("anthropic", "openai", "ollama"):
            if available.get(fb):
                chosen = fb
                break
    try:
        _check_spending_limit(db, user_id, chosen)
    except AppError as e:
        yield "error", {"detail": e.message, "code": e.code}
        return

    if chosen == "anthropic":
        gen = _stream_anthropic(messages, model=model, max_tokens=max_tokens,
                                temperature=temperature, api_key_override=api_key_override)
    elif chosen == "openai":
        gen = _stream_openai(messages, model=model, max_tokens=max_tokens,
                             temperature=temperature, api_key_override=api_key_override)
    else:
        gen = _stream_ollama(messages, model=model, max_tokens=max_tokens,
                             temperature=temperature)

    final_usage: dict | None = None
    try:
        for ev_type, payload in gen:
            if ev_type == "usage":
                final_usage = payload
            yield ev_type, payload
    except AppError as e:
        yield "error", {"detail": e.message, "code": e.code}
        _record_usage(db, user_id=user_id, provider=chosen, model=model or "?",
                      feature=feature, tin=0, tout=0, cost=Decimal("0"),
                      latency_ms=0, success=False)
        return
    except Exception as e:  # pragma: no cover
        logger.exception("stream_call unexpected error: {}", e)
        yield "error", {"detail": str(e), "code": "internal_error"}
        return

    if final_usage:
        try:
            cost = Decimal(str(final_usage.get("cost_usd", "0")))
        except Exception:
            cost = Decimal("0")
        _record_usage(
            db, user_id=user_id,
            provider=final_usage.get("provider", chosen),
            model=final_usage.get("model", model or "?"),
            feature=feature,
            tin=int(final_usage.get("tokens_in", 0)),
            tout=int(final_usage.get("tokens_out", 0)),
            cost=cost,
            latency_ms=int(final_usage.get("latency_ms", 0)),
            success=True,
        )
