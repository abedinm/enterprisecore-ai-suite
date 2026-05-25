"""Knowledge Hub ingest worker.

Polls the database for queued documents and runs them through the
parse → chunk → embed pipeline. Concurrency is intentionally one-at-a-time
to avoid hammering Ollama and to keep memory predictable when a single
large PDF is being embedded.
"""
from __future__ import annotations

from loguru import logger

from app.db.session import SessionLocal


def tick() -> int:
    """One pass: drain up to 5 queued documents. Returns count processed."""
    from app.services import knowledge as kn_svc
    with SessionLocal() as db:
        try:
            return kn_svc.process_pending(db, limit=5)
        except Exception as e:  # pragma: no cover
            logger.exception("ingest worker tick failed: {}", e)
            return 0
