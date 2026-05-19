"""AI Brain — providers, conversations, sentiment (AI calls mocked)."""
from __future__ import annotations

from unittest.mock import patch

from app.services import ai as ai_svc


def test_providers_endpoint(client, auth_headers):
    r = client.get("/api/v1/ai/providers", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    # With no keys configured in tests, anthropic/openai are False, ollama is reachable=True
    assert body["anthropic"] is False
    assert body["openai"] is False


def test_chat_with_mocked_provider(client, auth_headers):
    fake = ai_svc.AiResponse(
        text="Hello! How can I help?",
        provider="ollama", model="llama3.1",
        tokens_in=10, tokens_out=8,
        cost_usd=ai_svc.Decimal("0"), latency_ms=42,
    )
    with patch("app.services.ai.call", return_value=fake), \
         patch("app.api.v1.endpoints.ai.ai_svc.call", return_value=fake):
        r = client.post("/api/v1/ai/chat", headers=auth_headers, json={
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 50,
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "Hello! How can I help?"
    assert body["provider"] == "ollama"
    assert "conversation_id" in body


def test_sentiment_with_mocked_provider(client, auth_headers):
    fake = {"label": "positive", "score": 0.92, "summary": "Customer is happy."}
    with patch("app.services.ai.analyze_sentiment", return_value=fake), \
         patch("app.api.v1.endpoints.ai.ai_svc.analyze_sentiment", return_value=fake):
        r = client.post("/api/v1/ai/sentiment", headers=auth_headers,
                        json={"text": "I love this product!"})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "positive"
    assert body["score"] == 0.92
