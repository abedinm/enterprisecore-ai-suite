"""Streaming chat (SSE) tests — mocks provider so no real LLM is called."""
from __future__ import annotations

from unittest.mock import patch

from app.services import ai as ai_svc


def _fake_stream(*_args, **_kwargs):
    yield "token", {"text": "Hello"}
    yield "token", {"text": " world"}
    yield "usage", {
        "provider": "ollama", "model": "llama3.1",
        "tokens_in": 5, "tokens_out": 2, "cost_usd": "0",
        "latency_ms": 12, "text": "Hello world",
    }


def test_chat_stream_emits_sse_sequence(client, auth_headers):
    with patch("app.services.ai.stream_call", side_effect=_fake_stream):
        with client.stream(
            "POST", "/api/v1/ai/chat/stream",
            headers=auth_headers,
            json={
                "messages": [{"role": "user", "content": "Hi"}],
                "provider": "ollama",
                "max_tokens": 50,
            },
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            body = "".join(r.iter_text())

    assert "event: token" in body
    assert '"text": "Hello"' in body
    assert '"text": " world"' in body
    assert "event: usage" in body
    assert "event: done" in body
    assert '"conversation_id"' in body
