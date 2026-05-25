"""Pydantic schemas for the WebAuthn passkey surface.

The WebAuthn JSON shapes (PublicKeyCredentialCreationOptions, the
``navigator.credentials.create()`` result, etc.) are the standard ones
the browser API consumes — we don't try to model them strictly here.
The server-side ``options`` blobs are produced by the canonical
``webauthn`` library and passed through unchanged, so we type them as
plain dicts that the SPA serialises into the right Base64URL bytes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RegisterBeginOut(BaseModel):
    """Server response to register/begin.

    ``publicKey`` is the PublicKeyCredentialCreationOptions blob the
    browser feeds into ``navigator.credentials.create({publicKey})``.
    Challenge bytes are Base64URL-encoded by the webauthn library.
    """
    publicKey: dict[str, Any]


class RegisterFinishIn(BaseModel):
    """Body for register/finish.

    The SPA sends back exactly what ``navigator.credentials.create()``
    returned (a ``PublicKeyCredential``) plus an optional ``nickname``
    so the user can label the key in the UI.
    """
    credential: dict[str, Any]
    nickname: str | None = Field(default=None, max_length=120)


class RegisterFinishOut(BaseModel):
    id: str
    nickname: str | None
    created_at: datetime


class AuthenticateBeginIn(BaseModel):
    email: EmailStr | str = Field(min_length=3, max_length=255)


class AuthenticateBeginOut(BaseModel):
    publicKey: dict[str, Any]


class AuthenticateFinishIn(BaseModel):
    email: EmailStr | str = Field(min_length=3, max_length=255)
    credential: dict[str, Any]


class CredentialSummary(ORMModel):
    id: str
    nickname: str | None
    backed_up: bool
    transports: list[str]
    created_at: datetime
    last_used_at: datetime | None


class CredentialListOut(BaseModel):
    credentials: list[CredentialSummary]
