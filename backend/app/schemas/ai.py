"""AI Brain schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMModel


class ChatMessageIn(BaseModel):
    role: str = "user"
    content: str = Field(min_length=1)


class ChatRequestIn(BaseModel):
    conversation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    system: str | None = None
    messages: list[ChatMessageIn]
    max_tokens: int = 1024
    temperature: float = 0.7
    feature: str = "chat"


class ChatResponse(BaseModel):
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    latency_ms: int
    conversation_id: str | None = None


class ConversationOut(ORMModel):
    id: str
    title: str
    provider: str
    model: str | None
    created_at: datetime
    updated_at: datetime


class AiMessageOut(ORMModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tokens_in: int
    tokens_out: int
    created_at: datetime


class WriteRequestIn(BaseModel):
    kind: str  # email|memo|announcement|policy
    bullet_points: str
    tone: str = "professional"
    audience: str | None = None
    length: str = "medium"  # short|medium|long


class WriteResponseOut(BaseModel):
    text: str
    provider: str
    model: str


class SentimentIn(BaseModel):
    text: str = Field(min_length=1)


class SentimentOut(BaseModel):
    label: str
    score: float
    summary: str


class MeetingSummariseIn(BaseModel):
    transcript: str = Field(min_length=10)


class MeetingSummaryOut(BaseModel):
    summary: str
    key_decisions: list[str] = []
    action_items: list[dict] = []


class FinancialNarrationIn(BaseModel):
    period_start: date
    period_end: date


class HRInsightsIn(BaseModel):
    focus: str = "retention"


class InvoiceAnalysisIn(BaseModel):
    invoice_id: str


class ContractRiskIn(BaseModel):
    text: str = Field(min_length=20)


class ContractRiskOut(BaseModel):
    risk_score: float
    issues: list[dict] = []
    summary: str


class SmartSearchIn(BaseModel):
    query: str


class SmartSearchOut(BaseModel):
    interpretation: str
    answer: str
    sources: list[dict] = []


class RegexExplainIn(BaseModel):
    pattern: str


class ProviderStatus(BaseModel):
    anthropic: bool
    openai: bool
    ollama: bool


class UsageEntry(ORMModel):
    id: str
    user_id: str | None
    provider: str
    model: str
    feature: str
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    latency_ms: int
    success: bool
    occurred_at: datetime


class UsageSummary(BaseModel):
    total_calls: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: Decimal
    by_feature: dict[str, dict]
    by_provider: dict[str, dict]


class DailySpendPoint(BaseModel):
    date: str           # "YYYY-MM-DD"
    cost_usd: Decimal
    calls: int


class MySpendSummary(BaseModel):
    """Per-user spend summary with daily limit context."""
    user_id: str
    daily_spend_usd: Decimal        # last 24 hours
    daily_limit_usd: Decimal        # 0 = no limit
    limit_pct: Decimal              # 0-1 progress, capped at 1
    calls_24h: int
    tokens_24h: int
    cost_30d: Decimal               # last 30 days
    calls_30d: int
    tokens_30d: int
    by_provider_30d: dict[str, dict]
    timeline: list[DailySpendPoint] # daily spend for last 30 days


class ChatbotIn(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str
    welcome_message: str | None = None
    provider: str = "anthropic"
    model: str | None = None
    temperature: Decimal = Decimal("0.70")
    is_active: bool = True


class ChatbotOut(ORMModel):
    id: str
    name: str
    description: str | None
    system_prompt: str
    welcome_message: str | None
    provider: str
    model: str | None
    temperature: Decimal
    is_active: bool
    public_token: str | None
