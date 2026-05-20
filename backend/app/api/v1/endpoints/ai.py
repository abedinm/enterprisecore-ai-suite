"""AI Brain endpoints — chat, smart features, usage tracking, chatbot builder."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.ai import (
    AiConversation, AiMessage, AiUsageRecord, Chatbot, ChatbotMessage,
)
from app.models.finance import Customer, Expense, Invoice
from app.models.hr import Employee
from app.models.user import User, UserRole, SearchIndex
from app.schemas.ai import (
    AiMessageOut, ChatRequestIn, ChatResponse, ChatbotIn, ChatbotOut,
    ContractRiskIn, ContractRiskOut, ConversationOut, DailySpendPoint,
    FinancialNarrationIn, HRInsightsIn, InvoiceAnalysisIn, MeetingSummariseIn,
    MeetingSummaryOut, MySpendSummary, ProviderStatus, RegexExplainIn,
    SentimentIn, SentimentOut, SmartSearchIn, SmartSearchOut, UsageEntry,
    UsageSummary, WriteRequestIn, WriteResponseOut,
)
from app.services import ai as ai_svc
from app.services import finance as fin_svc

router = APIRouter()


# ---- Provider status ----------------------------------------------------
@router.get("/providers", response_model=ProviderStatus)
def providers(_: User = Depends(get_current_user)):
    return ProviderStatus(**ai_svc.available_providers())


# ---- Chat with conversation persistence --------------------------------
@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return db.scalars(
        select(AiConversation).where(AiConversation.user_id == current.id)
        .order_by(AiConversation.updated_at.desc()).limit(100)
    ).all()


@router.get("/conversations/{cid}/messages", response_model=list[AiMessageOut])
def list_conv_messages(cid: str, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    conv = db.get(AiConversation, cid)
    if not conv or conv.user_id != current.id:
        raise NotFoundError("Conversation not found")
    return db.scalars(
        select(AiMessage).where(AiMessage.conversation_id == cid).order_by(AiMessage.created_at)
    ).all()


@router.delete("/conversations/{cid}", status_code=204)
def delete_conversation(cid: str, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    conv = db.get(AiConversation, cid)
    if conv and conv.user_id == current.id:
        db.delete(conv)
        db.commit()


def _sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n".encode("utf-8")


@router.post("/chat/stream")
def chat_stream(payload: ChatRequestIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    """Server-sent events variant of /chat. Streams tokens incrementally
    and persists the conversation + assistant message after the stream ends."""
    messages = [ai_svc.AiMessage(role=m.role, content=m.content) for m in payload.messages]
    if payload.system:
        messages = [ai_svc.AiMessage(role="system", content=payload.system), *messages]

    if payload.conversation_id:
        conv = db.get(AiConversation, payload.conversation_id)
        if not conv or conv.user_id != current.id:
            raise NotFoundError("Conversation not found")
    else:
        title = payload.messages[0].content[:80] if payload.messages else "New conversation"
        conv = AiConversation(user_id=current.id, title=title,
                              provider=payload.provider or "ollama",
                              model=payload.model)
        db.add(conv)
        db.flush()
    for m in payload.messages:
        db.add(AiMessage(conversation_id=conv.id, role=m.role, content=m.content,
                         tokens_in=0, tokens_out=0))
    db.commit()

    def event_stream():
        full_parts: list[str] = []
        final_meta: dict = {}
        try:
            for ev_type, ev_payload in ai_svc.stream_call(
                messages=messages,
                provider=payload.provider, model=payload.model,
                max_tokens=payload.max_tokens, temperature=payload.temperature,
                feature=payload.feature, db=db, user_id=current.id,
            ):
                if ev_type == "token":
                    full_parts.append(ev_payload.get("text", ""))
                    yield _sse("token", ev_payload)
                elif ev_type == "usage":
                    final_meta = ev_payload
                    yield _sse("usage", {**ev_payload, "conversation_id": conv.id})
                elif ev_type == "error":
                    yield _sse("error", ev_payload)
        except Exception as e:  # pragma: no cover
            yield _sse("error", {"detail": str(e)})

        try:
            db.add(AiMessage(
                conversation_id=conv.id, role="assistant",
                content="".join(full_parts),
                tokens_in=int(final_meta.get("tokens_in", 0)),
                tokens_out=int(final_meta.get("tokens_out", 0)),
            ))
            conv.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            db.rollback()
        yield _sse("done", {"conversation_id": conv.id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequestIn, db: Session = Depends(get_db),
         current: User = Depends(get_current_user)):
    messages = [ai_svc.AiMessage(role=m.role, content=m.content) for m in payload.messages]
    if payload.system:
        messages = [ai_svc.AiMessage(role="system", content=payload.system), *messages]

    # Persist conversation
    if payload.conversation_id:
        conv = db.get(AiConversation, payload.conversation_id)
        if not conv or conv.user_id != current.id:
            raise NotFoundError("Conversation not found")
    else:
        title = payload.messages[0].content[:80] if payload.messages else "New conversation"
        conv = AiConversation(user_id=current.id, title=title,
                              provider=payload.provider or "anthropic", model=payload.model)
        db.add(conv)
        db.flush()

    for m in payload.messages:
        db.add(AiMessage(conversation_id=conv.id, role=m.role, content=m.content,
                         tokens_in=0, tokens_out=0))

    response = ai_svc.call(
        messages, provider=payload.provider, model=payload.model,
        max_tokens=payload.max_tokens, temperature=payload.temperature,
        feature=payload.feature, db=db, user_id=current.id,
    )
    db.add(AiMessage(conversation_id=conv.id, role="assistant", content=response.text,
                     tokens_in=response.tokens_in, tokens_out=response.tokens_out))
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return ChatResponse(
        text=response.text, provider=response.provider, model=response.model,
        tokens_in=response.tokens_in, tokens_out=response.tokens_out,
        cost_usd=response.cost_usd, latency_ms=response.latency_ms,
        conversation_id=conv.id,
    )


# ---- Writer -------------------------------------------------------------
@router.post("/writer", response_model=WriteResponseOut)
def writer(payload: WriteRequestIn, db: Session = Depends(get_db),
           current: User = Depends(get_current_user)):
    length_hint = {"short": "1 short paragraph", "medium": "2-3 paragraphs", "long": "4-6 paragraphs"}.get(payload.length, "2-3 paragraphs")
    prompt = (
        f"Write a {payload.kind} in a {payload.tone} tone for the audience: {payload.audience or 'general'}. "
        f"Target length: {length_hint}. Use the following bullet points as guidance.\n\n"
        f"BULLET POINTS:\n{payload.bullet_points}"
    )
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="system", content="You are a polished business writer."),
         ai_svc.AiMessage(role="user", content=prompt)],
        feature=f"write_{payload.kind}", db=db, user_id=current.id, max_tokens=900,
    )
    return WriteResponseOut(text=resp.text, provider=resp.provider, model=resp.model)


# ---- Smart features -----------------------------------------------------
@router.post("/sentiment", response_model=SentimentOut)
def sentiment(payload: SentimentIn, db: Session = Depends(get_db),
              current: User = Depends(get_current_user)):
    result = ai_svc.analyze_sentiment(payload.text, db=db, user_id=current.id)
    return SentimentOut(**result)


@router.post("/meeting/summarise", response_model=MeetingSummaryOut)
def summarise_meeting(payload: MeetingSummariseIn, db: Session = Depends(get_db),
                      current: User = Depends(get_current_user)):
    result = ai_svc.summarise_meeting(payload.transcript, db=db, user_id=current.id)
    return MeetingSummaryOut(**result)


@router.post("/regex/explain")
def explain_regex(payload: RegexExplainIn, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    text = ai_svc.explain_regex(payload.pattern, db=db, user_id=current.id)
    return {"pattern": payload.pattern, "explanation": text}


# ---- Financial narration -----------------------------------------------
@router.post("/financial-narration")
def financial_narration(payload: FinancialNarrationIn, db: Session = Depends(get_db),
                        current: User = Depends(get_current_user)):
    pnl = fin_svc.profit_and_loss(db, payload.period_start, payload.period_end)
    cf = fin_svc.cash_flow(db, payload.period_start, payload.period_end)
    summary = {
        "revenue": str(pnl["revenue"]), "expenses": str(pnl["operating_expenses"]),
        "net_income": str(pnl["net_income"]),
        "by_category": {k: str(v) for k, v in pnl["by_category"].items()},
        "cash_flow_totals": {k: str(v) for k, v in cf["totals"].items()},
    }
    prompt = (
        f"Write a concise CFO-style narration (3-5 paragraphs) of these financial results for "
        f"the period {payload.period_start} → {payload.period_end}.\n\nDATA:\n{summary}"
    )
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="system", content="You are an expert finance analyst."),
         ai_svc.AiMessage(role="user", content=prompt)],
        feature="financial_narration", db=db, user_id=current.id, max_tokens=700,
    )
    return {"narration": resp.text, "data": summary,
            "provider": resp.provider, "model": resp.model}


# ---- HR insights --------------------------------------------------------
@router.post("/hr-insights")
def hr_insights(payload: HRInsightsIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    headcount = db.scalar(select(func.count(Employee.id))) or 0
    avg_salary = db.scalar(select(func.coalesce(func.avg(Employee.salary), 0))) or Decimal("0")
    by_dept = db.execute(
        select(Employee.department, func.count(Employee.id))
        .group_by(Employee.department)
    ).all()
    snapshot = {
        "headcount": headcount, "avg_salary": float(avg_salary),
        "departments": {(d or "Unassigned"): c for d, c in by_dept},
    }
    prompt = (
        f"You are an HR strategy advisor. Given this snapshot, give 3-5 concrete, prioritized "
        f"recommendations focused on {payload.focus}.\n\nSNAPSHOT:\n{snapshot}"
    )
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="user", content=prompt)],
        feature="hr_insights", db=db, user_id=current.id, max_tokens=600,
    )
    return {"snapshot": snapshot, "insights": resp.text}


# ---- Invoice analyzer ---------------------------------------------------
@router.post("/invoice-analysis")
def invoice_analysis(payload: InvoiceAnalysisIn, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)):
    inv = db.get(Invoice, payload.invoice_id)
    if not inv:
        raise NotFoundError("Invoice not found")
    customer = db.get(Customer, inv.customer_id) if inv.customer_id else None
    history = db.scalars(
        select(Invoice).where(Invoice.customer_id == inv.customer_id, Invoice.id != inv.id)
        .order_by(Invoice.issue_date.desc()).limit(10)
    ).all() if inv.customer_id else []
    history_summary = [
        {"number": h.invoice_number, "total": str(h.total), "status": h.status,
         "issue_date": h.issue_date.isoformat()}
        for h in history
    ]
    prompt = (
        f"Analyze invoice {inv.invoice_number} (total {inv.total} {inv.currency}, status {inv.status}, "
        f"due {inv.due_date}). Customer: {customer.name if customer else 'Unknown'}. "
        f"History (last 10):\n{history_summary}\n\n"
        f"Provide: 1) payment risk score 0-1, 2) anomalies, 3) suggested follow-up. "
        f"Return strict JSON with keys: risk_score, anomalies, follow_up."
    )
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="user", content=prompt)],
        feature="invoice_analysis", db=db, user_id=current.id, max_tokens=400,
    )
    return {"invoice_id": inv.id, "analysis": resp.text}


# ---- Contract risk ------------------------------------------------------
@router.post("/contract-risk", response_model=ContractRiskOut)
def contract_risk(payload: ContractRiskIn, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    prompt = (
        "You are a contract review attorney. Read this clause-or-contract excerpt and return "
        "strict JSON only — no markdown — with shape:\n"
        '{"risk_score": 0..1, "issues": [{"clause": "...", "concern": "...", "severity": "low|medium|high"}], "summary": "..."}\n\n'
        f"TEXT:\n{payload.text}"
    )
    raw = ai_svc.smart_text(prompt, feature="contract_risk", db=db, user_id=current.id, max_tokens=800)
    import json
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if "\n" in raw:
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    try:
        data = json.loads(raw)
        return ContractRiskOut(
            risk_score=float(data.get("risk_score", 0.5)),
            issues=data.get("issues", []), summary=data.get("summary", ""),
        )
    except json.JSONDecodeError:
        return ContractRiskOut(risk_score=0.5, issues=[], summary=raw[:500])


# ---- Sales forecasting assistant ---------------------------------------
@router.post("/sales-forecast")
def sales_forecast_assistant(db: Session = Depends(get_db),
                            current: User = Depends(get_current_user)):
    from app.models.crm import Deal
    deals = db.scalars(select(Deal).where(~Deal.stage.in_(("won", "lost"))).limit(50)).all()
    summary = [
        {"title": d.title, "value": str(d.value), "stage": d.stage,
         "probability": str(d.probability),
         "expected_close": d.expected_close_date.isoformat() if d.expected_close_date else None}
        for d in deals
    ]
    prompt = (
        f"Given these open sales deals, identify the top 5 likely-to-close-this-quarter, "
        f"flag stalled ones, and project next-quarter revenue.\n\nDEALS:\n{summary}"
    )
    resp = ai_svc.call([ai_svc.AiMessage(role="user", content=prompt)],
                       feature="sales_forecast", db=db, user_id=current.id, max_tokens=700)
    return {"deals_analysed": len(summary), "analysis": resp.text}


# ---- Smart search -------------------------------------------------------
@router.post("/smart-search", response_model=SmartSearchOut)
def smart_search(payload: SmartSearchIn, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    # Pull top matches from the SearchIndex
    like = f"%{payload.query}%"
    matches = db.scalars(
        select(SearchIndex).where(
            SearchIndex.title.ilike(like) | SearchIndex.body.ilike(like)
        ).limit(10)
    ).all()
    sources = [{"id": m.id, "module": m.module, "title": m.title, "body": m.body[:200]} for m in matches]
    if not matches:
        return SmartSearchOut(
            interpretation=payload.query,
            answer="No indexed content matched. Try the structured filters on each module.",
            sources=[],
        )
    prompt = (
        f"User question: {payload.query}\n\n"
        f"Use only the following SOURCES to answer. Cite by [#].\n\n"
        + "\n".join(f"[{i + 1}] ({m['module']}) {m['title']}: {m['body']}" for i, m in enumerate(sources))
    )
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="system", content="You answer concisely with citations."),
         ai_svc.AiMessage(role="user", content=prompt)],
        feature="smart_search", db=db, user_id=current.id, max_tokens=500,
    )
    return SmartSearchOut(interpretation=payload.query, answer=resp.text, sources=sources)


# ---- Usage dashboard ----------------------------------------------------
@router.get("/usage", response_model=list[UsageEntry])
def usage_entries(limit: int = 100, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return db.scalars(
        select(AiUsageRecord).order_by(AiUsageRecord.occurred_at.desc()).limit(min(limit, 500))
    ).all()


@router.get("/usage/summary", response_model=UsageSummary)
def usage_summary(days: int = 30, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(select(AiUsageRecord).where(AiUsageRecord.occurred_at >= since)).all()
    total_calls = len(rows)
    tin = sum(r.tokens_in for r in rows)
    tout = sum(r.tokens_out for r in rows)
    cost = sum((r.cost_usd for r in rows), Decimal("0"))
    by_feature: dict[str, dict] = {}
    by_provider: dict[str, dict] = {}
    for r in rows:
        for key, bucket in ((r.feature, by_feature), (r.provider, by_provider)):
            entry = bucket.setdefault(key, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": Decimal("0")})
            entry["calls"] += 1
            entry["tokens_in"] += r.tokens_in
            entry["tokens_out"] += r.tokens_out
            entry["cost_usd"] += r.cost_usd
    return UsageSummary(
        total_calls=total_calls, total_tokens_in=tin, total_tokens_out=tout,
        total_cost_usd=cost, by_feature=by_feature, by_provider=by_provider,
    )


@router.get("/usage/my-summary", response_model=MySpendSummary)
def my_spend_summary(db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)) -> MySpendSummary:
    """Return the current user's own spend data with daily-limit context."""
    from app.core.config import settings as cfg
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_30d = now - timedelta(days=30)

    rows_24h = db.scalars(
        select(AiUsageRecord).where(
            AiUsageRecord.user_id == current.id,
            AiUsageRecord.occurred_at >= since_24h,
        )
    ).all()
    rows_30d = db.scalars(
        select(AiUsageRecord).where(
            AiUsageRecord.user_id == current.id,
            AiUsageRecord.occurred_at >= since_30d,
        )
    ).all()

    daily_spend = sum((r.cost_usd for r in rows_24h), Decimal("0"))
    limit = Decimal(str(cfg.ai_daily_usd_limit_per_user))
    limit_pct = (daily_spend / limit).quantize(Decimal("0.0001")) if limit > 0 else Decimal("0")
    limit_pct = min(limit_pct, Decimal("1"))

    cost_30d = sum((r.cost_usd for r in rows_30d), Decimal("0"))

    # per-provider breakdown for 30d
    by_provider: dict[str, dict] = {}
    for r in rows_30d:
        entry = by_provider.setdefault(r.provider, {
            "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": Decimal("0"),
        })
        entry["calls"] += 1
        entry["tokens_in"] += r.tokens_in
        entry["tokens_out"] += r.tokens_out
        entry["cost_usd"] += r.cost_usd

    # day-by-day timeline for last 30 days
    day_buckets: dict[str, dict] = {}
    for r in rows_30d:
        day_str = r.occurred_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        bucket = day_buckets.setdefault(day_str, {"cost_usd": Decimal("0"), "calls": 0})
        bucket["cost_usd"] += r.cost_usd
        bucket["calls"] += 1

    timeline = [
        DailySpendPoint(date=d, cost_usd=v["cost_usd"], calls=v["calls"])
        for d, v in sorted(day_buckets.items())
    ]

    return MySpendSummary(
        user_id=current.id,
        daily_spend_usd=daily_spend,
        daily_limit_usd=limit,
        limit_pct=limit_pct,
        calls_24h=len(rows_24h),
        tokens_24h=sum(r.tokens_in + r.tokens_out for r in rows_24h),
        cost_30d=cost_30d,
        calls_30d=len(rows_30d),
        tokens_30d=sum(r.tokens_in + r.tokens_out for r in rows_30d),
        by_provider_30d=by_provider,
        timeline=timeline,
    )


# ---- Chatbot builder ----------------------------------------------------
@router.get("/chatbots", response_model=list[ChatbotOut])
def list_chatbots(db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return db.scalars(select(Chatbot).order_by(Chatbot.created_at.desc())).all()


@router.post("/chatbots", response_model=ChatbotOut)
def create_chatbot(payload: ChatbotIn, db: Session = Depends(get_db),
                   current: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    bot = Chatbot(**payload.model_dump(), owner_id=current.id,
                  public_token=secrets.token_urlsafe(24))
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@router.post("/chatbots/{bid}/chat")
def chatbot_chat(bid: str, payload: dict, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    bot = db.get(Chatbot, bid)
    if not bot or not bot.is_active:
        raise NotFoundError("Chatbot not found or inactive")
    session_id = payload.get("session_id", secrets.token_hex(8))
    user_message = payload.get("message", "")
    db.add(ChatbotMessage(chatbot_id=bid, session_id=session_id, role="user", content=user_message))
    history = db.scalars(
        select(ChatbotMessage).where(
            ChatbotMessage.chatbot_id == bid, ChatbotMessage.session_id == session_id
        ).order_by(ChatbotMessage.created_at)
    ).all()
    msgs = [ai_svc.AiMessage(role="system", content=bot.system_prompt)]
    for h in history:
        msgs.append(ai_svc.AiMessage(role=h.role, content=h.content))
    resp = ai_svc.call(msgs, provider=bot.provider, model=bot.model,
                       temperature=float(bot.temperature), feature=f"chatbot_{bot.name}",
                       db=db, user_id=current.id, max_tokens=600)
    db.add(ChatbotMessage(chatbot_id=bid, session_id=session_id, role="assistant", content=resp.text))
    db.commit()
    return {"session_id": session_id, "response": resp.text, "provider": resp.provider}
