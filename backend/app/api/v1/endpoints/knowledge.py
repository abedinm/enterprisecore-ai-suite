"""Knowledge Hub endpoints — KBs, document ingest, retrieval, RAG chat,
Ollama model manager.

This module is the public HTTP surface for the AI Knowledge Hub. Heavy
lifting lives in ``app/services/knowledge.py``. M1 ships scaffolding —
later milestones fill in real behaviour.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError, ValidationFailed
from app.db.session import get_db
from app.models.knowledge import (
    KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeQuery,
)
from app.models.user import User, UserRole
from app.schemas.knowledge import (
    ChunkOut, DocOut, DocPasteIn, DocUrlIn, KbCreateIn, KbOut, KbUpdateIn,
    KnowledgeQueryOut, OllamaModelsOut, OllamaPullIn, RagChatIn, RetrieveIn,
    RetrieveOut,
)

router = APIRouter()


# ---- Helpers --------------------------------------------------------------
def _kb_or_404(db: Session, kb_id: str) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise NotFoundError("Knowledge base not found")
    return kb


def _doc_or_404(db: Session, kb_id: str, doc_id: str) -> KnowledgeDocument:
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc or doc.kb_id != kb_id:
        raise NotFoundError("Document not found")
    return doc


def _kb_to_out(db: Session, kb: KnowledgeBase) -> KbOut:
    doc_count = db.scalar(
        select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)
    ) or 0
    chunk_count = db.scalar(
        select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.kb_id == kb.id)
    ) or 0
    ready_count = db.scalar(
        select(func.count(KnowledgeDocument.id))
        .where(KnowledgeDocument.kb_id == kb.id, KnowledgeDocument.status == "ready")
    ) or 0
    return KbOut(
        id=kb.id, owner_id=kb.owner_id, name=kb.name, description=kb.description,
        embedding_provider=kb.embedding_provider, embedding_model=kb.embedding_model,
        embedding_dim=kb.embedding_dim, chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap, is_active=kb.is_active,
        created_at=kb.created_at, updated_at=kb.updated_at,
        document_count=doc_count, chunk_count=chunk_count, ready_count=ready_count,
    )


# ---- Knowledge Bases ------------------------------------------------------
@router.get("/kb", response_model=list[KbOut])
def list_kbs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    kbs = db.scalars(
        select(KnowledgeBase).order_by(KnowledgeBase.updated_at.desc())
    ).all()
    return [_kb_to_out(db, kb) for kb in kbs]


@router.post("/kb", response_model=KbOut, status_code=status.HTTP_201_CREATED)
def create_kb(
    payload: KbCreateIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    if payload.chunk_overlap >= payload.chunk_size:
        raise ValidationFailed("chunk_overlap must be smaller than chunk_size")
    kb = KnowledgeBase(
        owner_id=current.id,
        name=payload.name.strip(),
        description=payload.description,
        embedding_provider=payload.embedding_provider,
        embedding_model=payload.embedding_model,
        embedding_dim=payload.embedding_dim,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        is_active=True,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return _kb_to_out(db, kb)


@router.get("/kb/{kb_id}", response_model=KbOut)
def get_kb(kb_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _kb_to_out(db, _kb_or_404(db, kb_id))


@router.patch("/kb/{kb_id}", response_model=KbOut)
def update_kb(
    kb_id: str,
    payload: KbUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    kb = _kb_or_404(db, kb_id)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    new_size = data.get("chunk_size", kb.chunk_size)
    new_overlap = data.get("chunk_overlap", kb.chunk_overlap)
    if new_overlap >= new_size:
        raise ValidationFailed("chunk_overlap must be smaller than chunk_size")
    for key, value in data.items():
        setattr(kb, key, value)
    db.commit()
    db.refresh(kb)
    return _kb_to_out(db, kb)


@router.delete("/kb/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kb(
    kb_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    kb = _kb_or_404(db, kb_id)
    db.delete(kb)
    db.commit()


# ---- Documents (stubs filled in M3) --------------------------------------
@router.get("/kb/{kb_id}/documents", response_model=list[DocOut])
def list_documents(
    kb_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    _kb_or_404(db, kb_id)
    return db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.kb_id == kb_id)
        .order_by(KnowledgeDocument.created_at.desc())
    ).all()


@router.get("/kb/{kb_id}/documents/{doc_id}", response_model=DocOut)
def get_document(
    kb_id: str, doc_id: str,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    return _doc_or_404(db, kb_id, doc_id)


@router.post("/kb/{kb_id}/documents", response_model=DocOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.services import knowledge as kn_svc
    _kb_or_404(db, kb_id)
    doc = await kn_svc.ingest_upload(db, kb_id=kb_id, upload=file, user_id=current.id)
    return doc


@router.post("/kb/{kb_id}/documents/paste", response_model=DocOut, status_code=status.HTTP_202_ACCEPTED)
def paste_document(
    kb_id: str,
    payload: DocPasteIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.services import knowledge as kn_svc
    _kb_or_404(db, kb_id)
    return kn_svc.ingest_paste(db, kb_id=kb_id, name=payload.name, text=payload.text, user_id=current.id)


@router.post("/kb/{kb_id}/documents/url", response_model=DocOut, status_code=status.HTTP_202_ACCEPTED)
def url_document(
    kb_id: str,
    payload: DocUrlIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.services import knowledge as kn_svc
    _kb_or_404(db, kb_id)
    return kn_svc.ingest_url(db, kb_id=kb_id, url=payload.url, name=payload.name, user_id=current.id)


@router.delete("/kb/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    kb_id: str, doc_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    from app.services import knowledge as kn_svc
    doc = _doc_or_404(db, kb_id, doc_id)
    kn_svc.delete_document_blob(doc)
    db.delete(doc)
    db.commit()


@router.get("/kb/{kb_id}/documents/{doc_id}/chunks", response_model=list[ChunkOut])
def list_chunks(
    kb_id: str, doc_id: str,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    _doc_or_404(db, kb_id, doc_id)
    chunks = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == doc_id)
        .order_by(KnowledgeChunk.ordinal)
    ).all()
    out: list[ChunkOut] = []
    for c in chunks:
        out.append(ChunkOut(
            id=c.id, document_id=c.document_id, kb_id=c.kb_id, ordinal=c.ordinal,
            text=c.text, page_number=c.page_number, char_start=c.char_start,
            char_end=c.char_end, token_count=c.token_count,
            embedding_model=c.embedding_model, has_embedding=bool(c.embedding),
            created_at=c.created_at,
        ))
    return out


@router.post("/kb/{kb_id}/documents/{doc_id}/reindex", response_model=DocOut)
def reindex_document(
    kb_id: str, doc_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    from app.services import knowledge as kn_svc
    doc = _doc_or_404(db, kb_id, doc_id)
    kn_svc.requeue_document(db, doc, reset_chunks=True)
    return doc


@router.post("/kb/{kb_id}/reindex")
def reindex_kb(
    kb_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    from app.services import knowledge as kn_svc
    _kb_or_404(db, kb_id)
    count = kn_svc.requeue_kb(db, kb_id)
    return {"kb_id": kb_id, "queued": count}


# ---- Retrieval + RAG -----------------------------------------------------
@router.post("/kb/{kb_id}/query", response_model=RetrieveOut)
def retrieve_only(
    kb_id: str,
    payload: RetrieveIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.services import knowledge as kn_svc
    _kb_or_404(db, kb_id)
    return kn_svc.retrieve(
        db, kb_ids=[kb_id], query=payload.query, top_k=payload.top_k, user_id=current.id,
    )


@router.post("/rag/chat")
def rag_chat(
    payload: RagChatIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Streaming RAG chat. Returns text/event-stream with token, usage, done events."""
    from app.services import knowledge as kn_svc
    for kid in payload.kb_ids:
        _kb_or_404(db, kid)
    return StreamingResponse(
        kn_svc.rag_chat_stream(db=db, user_id=current.id, payload=payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/queries", response_model=list[KnowledgeQueryOut])
def list_queries(
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.scalars(
        select(KnowledgeQuery)
        .order_by(KnowledgeQuery.created_at.desc())
        .limit(min(limit, 500))
    ).all()


# ---- Ollama model manager ------------------------------------------------
@router.get("/models/ollama", response_model=OllamaModelsOut)
def list_ollama_models(_: User = Depends(get_current_user)):
    from app.services import knowledge as kn_svc
    return kn_svc.list_ollama_models()


@router.post("/models/ollama/pull")
def pull_ollama_model(
    payload: OllamaPullIn,
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    from app.services import knowledge as kn_svc
    return StreamingResponse(
        kn_svc.pull_ollama_model_stream(payload.name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
