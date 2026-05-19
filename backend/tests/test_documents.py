"""Documents module smoke tests."""
from __future__ import annotations


def test_document_create_edit_pdf(client, auth_headers):
    create = client.post("/api/v1/documents", headers=auth_headers, json={
        "title": "Test policy", "content": "# Hello\n\nWorld.", "visibility": "private",
    })
    assert create.status_code == 200, create.text
    doc = create.json()
    did = doc["id"]

    patch = client.patch(f"/api/v1/documents/{did}", headers=auth_headers, json={
        "title": "Test policy v2", "content": "# Hello\n\nWorld v2.", "visibility": "private",
    })
    assert patch.status_code == 200

    versions = client.get(f"/api/v1/documents/{did}/versions", headers=auth_headers)
    assert versions.status_code == 200
    assert len(versions.json()) >= 1

    pdf = client.get(f"/api/v1/documents/{did}/pdf", headers=auth_headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_document_signature(client, auth_headers):
    doc = client.post("/api/v1/documents", headers=auth_headers, json={
        "title": "Contract", "content": "Signature required."
    }).json()
    sig = client.post("/api/v1/documents/signatures", headers=auth_headers, json={
        "document_id": doc["id"], "signer_name": "Alice", "signer_email": "alice@example.com",
    })
    assert sig.status_code == 200, sig.text
    body = sig.json()
    assert body["signer_name"] == "Alice"
    assert len(body["signature_hash"]) == 64  # SHA-256 hex
