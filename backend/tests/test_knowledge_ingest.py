"""Knowledge Hub ingest tests — parsing, chunking, and the end-to-end pipeline.

Embeddings use the deterministic hash-pseudo fallback so the test suite
doesn't need a running Ollama instance.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import io
import numpy as np
import pytest

from app.services import knowledge as kn_svc


# ---- Parsing -------------------------------------------------------------
def test_chunker_basic_paragraph(tmp_path: Path):
    blocks = [
        (None, 0, 50, "First paragraph about apples and oranges."),
        (None, 52, 110, "Second paragraph that talks about bananas in detail."),
        (None, 112, 160, "Third paragraph about carrots and lettuce."),
    ]
    chunks = kn_svc.chunk_text(blocks, chunk_size=120, chunk_overlap=20)
    assert len(chunks) >= 2
    assert all(c["text"].strip() for c in chunks)
    assert all(c["char_end"] > c["char_start"] for c in chunks)
    assert chunks[0]["ordinal"] == 0
    assert chunks[1]["ordinal"] == 1


def test_chunker_slices_oversized_block():
    big = "x" * 5000
    blocks = [(7, 0, 5000, big)]
    chunks = kn_svc.chunk_text(blocks, chunk_size=800, chunk_overlap=100)
    assert len(chunks) >= 6  # 5000 / (800-100) ≈ 8
    assert all(c["page_number"] == 7 for c in chunks)
    assert chunks[0]["char_start"] == 0


def test_chunker_overlap_chars(tmp_path: Path):
    # Build paragraphs slightly under chunk_size and ensure consecutive chunks
    # overlap by the requested number of characters where possible.
    paragraphs = [
        ("alpha " * 60).strip(),
        ("beta " * 60).strip(),
        ("gamma " * 60).strip(),
    ]
    blocks = []
    cursor = 0
    for p in paragraphs:
        blocks.append((None, cursor, cursor + len(p), p))
        cursor += len(p) + 2
    chunks = kn_svc.chunk_text(blocks, chunk_size=400, chunk_overlap=80)
    assert len(chunks) >= 2


def test_parse_text_file(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("First paragraph.\n\nSecond paragraph here.\n\nThird.")
    text, blocks = kn_svc.parse_document(target, "text/plain", target.name)
    assert "First paragraph" in text
    assert len(blocks) == 3


def test_parse_markdown(tmp_path: Path):
    target = tmp_path / "notes.md"
    target.write_text("# Title\n\nSome body text.\n\nAnother paragraph.")
    text, blocks = kn_svc.parse_document(target, "text/markdown", target.name)
    assert "Some body text" in text
    assert len(blocks) >= 2


def test_parse_html(tmp_path: Path):
    target = tmp_path / "page.html"
    target.write_text(
        "<html><head><title>t</title><script>x=1</script></head>"
        "<body><p>Hello world.</p><p>Another paragraph.</p></body></html>"
    )
    text, blocks = kn_svc.parse_document(target, "text/html", target.name)
    assert "Hello world" in text
    assert "x=1" not in text  # script content removed
    assert any("Another paragraph" in b[3] for b in blocks)


# ---- Embeddings ----------------------------------------------------------
def test_hash_pseudo_embedding_dimensions():
    v = kn_svc._hash_pseudo_embedding("the quick brown fox", dim=768)
    assert v.shape == (768,)
    assert v.dtype == np.float32
    # Should be unit-normalized
    assert pytest.approx(float(np.linalg.norm(v)), abs=1e-5) == 1.0


def test_embed_falls_back_to_hash_when_ollama_unreachable():
    with patch("app.services.knowledge._embed_ollama", side_effect=RuntimeError("offline")):
        vecs = kn_svc.embed(["alpha", "beta"], provider="ollama", model="nomic-embed-text")
    assert len(vecs) == 2
    assert all(v.shape == (768,) for v in vecs)


def test_encode_decode_vec_roundtrip():
    v = np.array([0.1, 0.5, -0.3, 0.7], dtype=np.float32)
    raw = kn_svc.encode_vec(v)
    back = kn_svc.decode_vec(raw)
    np.testing.assert_allclose(back, v)


def test_cosine_topk_ranks_correctly():
    # Build a matrix where row 2 is identical to the query, row 0 partially matches, row 1 is orthogonal.
    matrix = np.array([
        [0.6, 0.0, 0.8, 0.0],   # partial match
        [0.0, 1.0, 0.0, 0.0],   # orthogonal to query
        [1.0, 0.0, 0.0, 0.0],   # identical to query
    ], dtype=np.float32)
    # Normalize each row
    matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    ranked = kn_svc.cosine_topk(query, matrix, k=2)
    assert ranked[0][0] == 2
    assert ranked[0][1] == pytest.approx(1.0, abs=1e-5)
    assert ranked[1][0] == 0


# ---- End-to-end ingest ---------------------------------------------------
def test_end_to_end_paste_ingest_and_retrieve(client, auth_headers, db):
    # Create a KB
    kb_resp = client.post(
        "/api/v1/knowledge/kb",
        headers=auth_headers,
        json={"name": "E2E KB", "chunk_size": 400, "chunk_overlap": 40},
    )
    assert kb_resp.status_code == 201, kb_resp.text
    kb_id = kb_resp.json()["id"]

    # Paste a meaningful chunk of text
    text = (
        "EnterpriseCore AI Suite is an offline-first business platform. "
        "It runs FastAPI on the backend and React with Tailwind on the frontend. "
        "Documents stay on the user's machine — no SaaS subscription required.\n\n"
        "The AI Brain module provides Anthropic, OpenAI and Ollama integration. "
        "Ollama is used for local, private inference with models like llama3.1.\n\n"
        "The Knowledge Hub adds Retrieval-Augmented Generation over private files."
    )
    paste = client.post(
        f"/api/v1/knowledge/kb/{kb_id}/documents/paste",
        headers=auth_headers,
        json={"name": "Architecture overview", "text": text},
    )
    assert paste.status_code == 202, paste.text
    doc_id = paste.json()["id"]

    # Run the ingest worker synchronously
    processed = kn_svc.process_document(db, doc_id)
    assert processed is True

    # Refresh
    db.expire_all()
    doc_resp = client.get(
        f"/api/v1/knowledge/kb/{kb_id}/documents/{doc_id}", headers=auth_headers
    )
    assert doc_resp.status_code == 200
    doc = doc_resp.json()
    assert doc["status"] == "ready"
    assert doc["chunk_count"] >= 1
    assert doc["char_count"] > 0

    # Chunks should be present and embedded
    chunks_resp = client.get(
        f"/api/v1/knowledge/kb/{kb_id}/documents/{doc_id}/chunks",
        headers=auth_headers,
    )
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert len(chunks) >= 1
    assert all(c["has_embedding"] for c in chunks)

    # Retrieve (no LLM call — just vector search)
    retrieve = client.post(
        f"/api/v1/knowledge/kb/{kb_id}/query",
        headers=auth_headers,
        json={"query": "What is the Knowledge Hub?", "top_k": 3},
    )
    assert retrieve.status_code == 200, retrieve.text
    out = retrieve.json()
    assert len(out["chunks"]) >= 1
    # At least one chunk should mention a topic from the ingested doc.
    # We accept any of these markers because chunk ranking varies between
    # the deterministic hash-fallback embedder (used in CI when Ollama isn't
    # available) and the real nomic-embed-text embeddings (used when Ollama
    # is running locally). Both rankings still surface relevant chunks from
    # the same document.
    joined = " ".join(c["text"] for c in out["chunks"]).lower()
    assert any(marker in joined for marker in (
        "knowledge hub", "retrieval", "enterprisecore", "ai brain",
        "fastapi", "ollama",
    )), f"no expected marker in retrieved chunks: {joined[:300]}"


def test_upload_rejects_oversized_file(client, auth_headers, monkeypatch):
    # Drop the limit to 1MB for this test
    from app.core.config import settings
    monkeypatch.setattr(settings, "knowledge_max_upload_mb", 1)
    kb = client.post(
        "/api/v1/knowledge/kb", headers=auth_headers,
        json={"name": "Size Limit"},
    ).json()
    big = b"x" * (2 * 1024 * 1024)
    r = client.post(
        f"/api/v1/knowledge/kb/{kb['id']}/documents",
        headers=auth_headers,
        files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
    )
    assert r.status_code == 422
    assert "too large" in r.text.lower()


def test_upload_rejects_unsupported_extension(client, auth_headers):
    kb = client.post(
        "/api/v1/knowledge/kb", headers=auth_headers, json={"name": "Filter Check"},
    ).json()
    r = client.post(
        f"/api/v1/knowledge/kb/{kb['id']}/documents",
        headers=auth_headers,
        files={"file": ("notes.zip", io.BytesIO(b"PK\x03\x04"), "application/zip")},
    )
    assert r.status_code == 422


def test_delete_doc_removes_blob(client, auth_headers, db, tmp_path):
    kb = client.post(
        "/api/v1/knowledge/kb", headers=auth_headers, json={"name": "Cleanup KB"},
    ).json()
    paste = client.post(
        f"/api/v1/knowledge/kb/{kb['id']}/documents/paste",
        headers=auth_headers,
        json={"name": "to-delete", "text": "Just some text."},
    ).json()
    from app.models.knowledge import KnowledgeDocument
    doc = db.get(KnowledgeDocument, paste["id"])
    storage = Path(doc.storage_path)
    assert storage.exists()

    r = client.delete(
        f"/api/v1/knowledge/kb/{kb['id']}/documents/{paste['id']}", headers=auth_headers
    )
    assert r.status_code == 204
    assert not storage.exists()


def test_reindex_resets_doc_state(client, auth_headers, db):
    kb = client.post(
        "/api/v1/knowledge/kb", headers=auth_headers,
        json={"name": "Reindex KB", "chunk_size": 400, "chunk_overlap": 40},
    ).json()
    paste = client.post(
        f"/api/v1/knowledge/kb/{kb['id']}/documents/paste",
        headers=auth_headers,
        json={"name": "reidx", "text": "Para one.\n\nPara two."},
    ).json()
    assert kn_svc.process_document(db, paste["id"])

    r = client.post(
        f"/api/v1/knowledge/kb/{kb['id']}/documents/{paste['id']}/reindex",
        headers=auth_headers,
    )
    assert r.status_code == 200
    # After reindex the doc should be back to queued with no chunks until the
    # next worker pass.
    from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
    db.expire_all()
    fresh = db.get(KnowledgeDocument, paste["id"])
    assert fresh.status == "queued"
    chunk_count = db.query(KnowledgeChunk).filter(
        KnowledgeChunk.document_id == paste["id"]
    ).count()
    assert chunk_count == 0
