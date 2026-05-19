"""Tests for the avatar upload endpoints (POST/DELETE /auth/me/avatar).

Covers:
  - Happy path: PNG upload sets user.avatar_url and writes a file to disk
  - Wrong content-type rejected with 422
  - Oversized payload rejected with 422
  - Empty payload rejected with 422
  - Garbage bytes with valid content-type rejected with 422
  - Delete is idempotent (succeeds even when no avatar exists)
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.user import User


def _png_bytes(size: tuple[int, int] = (128, 128), color: tuple = (200, 30, 30, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(size: tuple[int, int] = (64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 200, 30)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _avatar_path(user_id: str) -> Path:
    return settings.storage_dir / "uploads" / "avatars" / f"{user_id}.png"


def test_upload_png_sets_avatar(client, auth_headers, session_factory):
    payload = _png_bytes()
    r = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth_headers,
        files={"file": ("me.png", payload, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["avatar_url"]
    assert body["avatar_url"].startswith("/files/avatars/")
    assert body["avatar_url"].endswith(".png")

    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@local"))
        path = _avatar_path(admin.id)
        assert path.exists()
        assert path.stat().st_size > 0


def test_upload_jpeg_converted_to_png(client, auth_headers, session_factory):
    payload = _jpeg_bytes()
    r = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth_headers,
        files={"file": ("me.jpg", payload, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    # On disk we always store PNG regardless of input format.
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@local"))
    path = _avatar_path(admin.id)
    assert path.suffix == ".png"


def test_upload_unsupported_content_type_rejected(client, auth_headers):
    r = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth_headers,
        files={"file": ("evil.svg", b"<svg/>", "image/svg+xml")},
    )
    assert r.status_code == 422
    assert "Unsupported file type" in r.json()["detail"]


def test_upload_oversized_rejected(client, auth_headers):
    # 3 MB of zeros, claimed as PNG
    payload = b"\x00" * (3 * 1024 * 1024)
    r = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth_headers,
        files={"file": ("big.png", payload, "image/png")},
    )
    assert r.status_code == 422
    assert "too large" in r.json()["detail"].lower()


def test_upload_garbage_with_png_mime_rejected(client, auth_headers):
    r = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth_headers,
        files={"file": ("garbage.png", b"this is not an image", "image/png")},
    )
    assert r.status_code == 422
    assert "image" in r.json()["detail"].lower()


def test_upload_empty_rejected(client, auth_headers):
    r = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth_headers,
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert r.status_code == 422


def test_delete_avatar(client, auth_headers, session_factory):
    # Plant an avatar first
    client.post(
        "/api/v1/auth/me/avatar",
        headers=auth_headers,
        files={"file": ("me.png", _png_bytes(), "image/png")},
    )
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@local"))
    path = _avatar_path(admin.id)
    assert path.exists()

    r = client.delete("/api/v1/auth/me/avatar", headers=auth_headers)
    assert r.status_code == 204

    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@local"))
        assert admin.avatar_url is None
    assert not path.exists()


def test_delete_idempotent_when_no_avatar(client, auth_headers):
    # Ensure no avatar is set
    client.delete("/api/v1/auth/me/avatar", headers=auth_headers)
    # Second delete should still be 204
    r = client.delete("/api/v1/auth/me/avatar", headers=auth_headers)
    assert r.status_code == 204
