"""Knowledge Hub schemas — KBs, documents, chunks, queries, models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai import ChatMessageIn
from app.schemas.common import ORMModel


# ---- Knowledge Base ------------------------------------------------------
class KbCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = Field(default=768, ge=64, le=8192)
    chunk_size: int = Field(default=800, ge=200, le=4000)
    chunk_overlap: int = Field(default=100, ge=0, le=800)


class KbUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = Field(default=None, ge=64, le=8192)
    chunk_size: int | None = Field(default=None, ge=200, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=800)
    is_active: bool | None = None


class KbOut(ORMModel):
    id: str
    owner_id: str | None
    name: str
    description: str | None
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    chunk_count: int = 0
    ready_count: int = 0


# ---- Documents -----------------------------------------------------------
class DocPasteIn(BaseModel):
    name: str = Field(min_length=1, max_length=400)
    text: str = Field(min_length=1)


class DocUrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    name: str | None = None


class DocOut(ORMModel):
    id: str
    kb_id: str
    name: str
    source_type: str
    source_ref: str | None
    mime_type: str | None
    byte_size: int
    status: str
    error_message: str | None
    page_count: int
    char_count: int
    chunk_count: int
    ingested_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChunkOut(ORMModel):
    id: str
    document_id: str
    kb_id: str
    ordinal: int
    text: str
    page_number: int | None
    char_start: int
    char_end: int
    token_count: int
    embedding_model: str | None
    has_embedding: bool = False
    created_at: datetime


# ---- Retrieval + RAG -----------------------------------------------------
class RetrieveIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=6, ge=1, le=50)


class RetrievedChunkOut(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    kb_id: str
    kb_name: str
    text: str
    page_number: int | None
    score: float


class RetrieveOut(BaseModel):
    query: str
    chunks: list[RetrievedChunkOut]
    embedding_provider: str
    embedding_model: str
    latency_ms: int


class RagChatIn(BaseModel):
    kb_ids: list[str] = Field(min_length=1, max_length=10)
    messages: list[ChatMessageIn] = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    top_k: int = Field(default=6, ge=1, le=20)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64, le=8192)
    conversation_id: str | None = None
    stream: bool = True


class KnowledgeQueryOut(ORMModel):
    id: str
    user_id: str | None
    question: str
    answer: str | None
    provider: str | None
    model: str | None
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    created_at: datetime


# ---- Ollama model manager ------------------------------------------------
class OllamaModelOut(BaseModel):
    name: str
    size_bytes: int = 0
    modified_at: str | None = None
    parameter_size: str | None = None
    family: str | None = None


class OllamaModelsOut(BaseModel):
    models: list[OllamaModelOut]
    host: str
    reachable: bool


class OllamaPullIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class StreamChatIn(BaseModel):
    """Body for POST /ai/chat/stream — identical to ChatRequestIn but
    declared separately so swagger lists the streaming variant distinctly."""

    model_config = ConfigDict(extra="forbid")
    conversation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    system: str | None = None
    messages: list[ChatMessageIn]
    max_tokens: int = 1024
    temperature: float = 0.7
    feature: str = "chat"
