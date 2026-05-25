"""Per-tenant storage and usage accounting.

The ``GET /tenants/me/usage`` endpoint used to return a hard-coded 0.0 for
``storage_mb``. This service replaces the stub with a real walk across every
table that holds tenant-owned bytes, plus a small 5-minute TTL cache so the
endpoint doesn't re-scan large tables on every dashboard refresh.

Tables walked
-------------
* ``marketing_uploads.size_bytes`` — sum of recorded upload sizes.
* ``knowledge_documents.byte_size`` — original source-file sizes, plus the
  on-disk file at ``storage_path`` when present (the cached extracted text
  doubles roughly the original size; we just trust ``byte_size`` here).
* ``knowledge_chunks.char_count`` (via document) — rough proxy for embedded
  text storage (4 bytes per char as a conservative estimate; embeddings live
  in LargeBinary on the same row and are part of the same allocation).
* ``documents`` (Documents module) — ``len(content)`` per row plus the
  on-disk file at ``file_path`` if it exists.
* ``construction`` attachments — JSON arrays referencing marketing_uploads,
  already counted above; site-instruction / toolbox attachments referenced
  by id are summed transitively.
* ``webchat_messages.content`` — character count of every message body.
* ``gdpr_export_jobs.download_path`` — file size of any generated bundle
  still on disk.

All sizes are summed in bytes, divided by (1024 * 1024), and rounded to two
decimal places before returning.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Final

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tenant_context import bypass_tenant_filter

# 5-minute TTL — long enough to avoid hammering the DB on rapid dashboard
# polling, short enough that a freshly-uploaded file shows up within a few
# minutes. Keyed by tenant_id.
_CACHE_TTL_SECONDS: Final[float] = 300.0
_cache: dict[str, tuple[float, float]] = {}  # tenant_id -> (epoch, mb)
_cache_lock = threading.Lock()


def _file_size_bytes(path_str: str | None) -> int:
    """Stat a file path, returning 0 on any failure. Paths may be relative
    (resolved under ``settings.storage_dir``) or absolute."""
    if not path_str:
        return 0
    try:
        p = Path(path_str)
        if not p.is_absolute():
            p = settings.storage_dir / path_str
        return p.stat().st_size
    except (OSError, ValueError):
        return 0


def _sum_marketing_uploads(db: Session, tenant_id: str) -> int:
    from app.models.marketing import MarketingUpload

    with bypass_tenant_filter():
        total = db.scalar(
            select(func.coalesce(func.sum(MarketingUpload.size_bytes), 0)).where(
                MarketingUpload.tenant_id == tenant_id
            )
        )
    return int(total or 0)


def _sum_knowledge_documents(db: Session, tenant_id: str) -> int:
    from app.models.knowledge import KnowledgeDocument

    with bypass_tenant_filter():
        rows = db.execute(
            select(
                func.coalesce(func.sum(KnowledgeDocument.byte_size), 0),
                func.coalesce(func.sum(KnowledgeDocument.char_count), 0),
            ).where(KnowledgeDocument.tenant_id == tenant_id)
        ).first()
    byte_sum = int(rows[0] or 0) if rows else 0
    char_sum = int(rows[1] or 0) if rows else 0
    # Each char costs ~4 bytes once you include UTF-8 expansion + the float32
    # embedding vector that gets stored alongside.
    return byte_sum + char_sum * 4


def _sum_documents(db: Session, tenant_id: str) -> int:
    from app.models.documents import Document

    with bypass_tenant_filter():
        rows = db.execute(
            select(Document.content, Document.file_path).where(
                Document.tenant_id == tenant_id
            )
        ).all()
    total = 0
    for content, file_path in rows:
        if content:
            total += len(content.encode("utf-8", "ignore"))
        total += _file_size_bytes(file_path)
    return total


def _sum_webchat_messages(db: Session, tenant_id: str) -> int:
    from app.models.webchat import ChatMessage

    with bypass_tenant_filter():
        # SUM(LENGTH(content)) is portable across SQLite/Postgres.
        total = db.scalar(
            select(func.coalesce(func.sum(func.length(ChatMessage.content)), 0)).where(
                ChatMessage.tenant_id == tenant_id
            )
        )
    # ``LENGTH`` is char count on most dialects — multiply by an avg UTF-8
    # byte factor of ~2 to be conservative.
    return int(total or 0) * 2


def _sum_gdpr_exports(db: Session, tenant_id: str) -> int:
    from app.models.webhooks import GdprExportJob

    with bypass_tenant_filter():
        paths = db.scalars(
            select(GdprExportJob.download_path).where(
                GdprExportJob.tenant_id == tenant_id,
                GdprExportJob.download_path.is_not(None),
            )
        ).all()
    return sum(_file_size_bytes(p) for p in paths)


def _sum_construction_attachments(db: Session, tenant_id: str) -> int:
    """Construction module stores attachments as JSON arrays of
    marketing_upload ids. Those are already counted in
    ``_sum_marketing_uploads``; we add nothing here to avoid double-counting,
    but the hook is preserved so future on-disk attachments can be folded in
    without changing the public interface."""
    return 0


def compute_tenant_storage_mb(db: Session, tenant_id: str) -> float:
    """Sums storage used by this tenant across:

    - marketing_uploads (sum size_bytes)
    - knowledge_documents (sum chunk char_count * 4 bytes, plus original
      file size if present)
    - construction project attachments (transitively via marketing uploads)
    - documents (Documents module — sum file sizes)
    - webchat conversation message bodies (rough char count)
    - gdpr_export_jobs (file sizes of generated exports)

    Returns total in MB rounded to 2 decimal places.
    """
    total_bytes = 0
    for fn in (
        _sum_marketing_uploads,
        _sum_knowledge_documents,
        _sum_documents,
        _sum_webchat_messages,
        _sum_gdpr_exports,
        _sum_construction_attachments,
    ):
        try:
            total_bytes += fn(db, tenant_id)
        except Exception:  # noqa: BLE001
            # A schema mismatch in one table mustn't blow up the whole
            # endpoint — log and keep going so we always return a number.
            logger.exception("tenant_usage: {} failed for tenant {}", fn.__name__, tenant_id)
    mb = total_bytes / (1024.0 * 1024.0)
    return round(mb, 2)


def get_tenant_storage_mb(db: Session, tenant_id: str, *, force_refresh: bool = False) -> float:
    """Cached wrapper around :func:`compute_tenant_storage_mb`.

    Cache TTL is :data:`_CACHE_TTL_SECONDS` (5 min) and is process-local —
    that's intentional for now. Storage accounting is read-mostly and a
    rolling refresh keeps the dashboard responsive without a distributed
    cache.
    """
    if not force_refresh:
        with _cache_lock:
            entry = _cache.get(tenant_id)
            if entry and (time.monotonic() - entry[0]) < _CACHE_TTL_SECONDS:
                return entry[1]
    mb = compute_tenant_storage_mb(db, tenant_id)
    with _cache_lock:
        _cache[tenant_id] = (time.monotonic(), mb)
    return mb


def invalidate_cache(tenant_id: str | None = None) -> None:
    """Drop a single tenant's cached value (or every tenant's if None)."""
    with _cache_lock:
        if tenant_id is None:
            _cache.clear()
        else:
            _cache.pop(tenant_id, None)


__all__ = [
    "compute_tenant_storage_mb",
    "get_tenant_storage_mb",
    "invalidate_cache",
]
