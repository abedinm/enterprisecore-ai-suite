"""Communication module smoke tests."""
from __future__ import annotations


def test_message_thread_and_send(client, auth_headers):
    t = client.post("/api/v1/communication/threads", headers=auth_headers,
                    json={"title": "Test thread"})
    assert t.status_code == 200
    tid = t.json()["id"]

    m = client.post(f"/api/v1/communication/threads/{tid}/messages", headers=auth_headers,
                    json={"thread_id": tid, "body": "Hello, world."})
    assert m.status_code == 200
    assert m.json()["body"] == "Hello, world."

    listing = client.get(f"/api/v1/communication/threads/{tid}/messages", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_announcement_create(client, auth_headers):
    a = client.post("/api/v1/communication/announcements", headers=auth_headers,
                    json={"title": "All-hands Friday", "body": "Coffee provided.",
                          "audience": "all"})
    assert a.status_code == 200


def test_wiki_create_and_search(client, auth_headers):
    w = client.post("/api/v1/communication/wiki", headers=auth_headers, json={
        "title": "Onboarding guide", "body": "Step 1: Read this. Step 2: ...",
    })
    assert w.status_code == 200
    listing = client.get("/api/v1/communication/wiki", headers=auth_headers,
                         params={"q": "Onboarding"})
    assert listing.status_code == 200
    assert any(p["title"] == "Onboarding guide" for p in listing.json())


def test_feedback_submission(client, auth_headers):
    f = client.post("/api/v1/communication/feedback", headers=auth_headers, json={
        "subject": "Love the dashboards", "body": "Great work team!",
        "category": "praise",
    })
    assert f.status_code == 200
