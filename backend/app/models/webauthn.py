"""WebAuthn / FIDO2 passkey credentials.

One row per registered authenticator (security key, Touch ID, Windows
Hello, password manager passkey). A user can have many — each from a
different device or each as a backup.

Tenant-scoped via :class:`TenantMixin`: a passkey registered under
Tenant A cannot be used to sign in as the same email under Tenant B,
which is the canonical defence against cross-tenant credential reuse
when an org runs multiple isolated tenants in the same install.

``credential_id`` is the WebAuthn credential identifier the authenticator
returned during registration — opaque bytes, unique across all
credentials. We index it for the authentication-finish path which has
to look up the credential without knowing the user.

``sign_count`` is the WebAuthn rolling counter the authenticator
increments on every successful assertion. We persist the latest value
and reject an assertion whose counter is less-than-or-equal to what we
stored — the canonical replay defence baked into the spec.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class WebAuthnCredential(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "webauthn_credentials"

    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Raw credential id returned by the authenticator during registration.
    # Globally unique per the WebAuthn spec; we enforce uniqueness so the
    # authenticate-finish lookup is well-defined.
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True, index=True)
    # COSE-encoded public key the authenticator returned. We store the
    # raw bytes the webauthn library hands us and feed them straight back
    # in on assertion verification.
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # The authenticator AAGUID — identifies the model of authenticator.
    aaguid: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Has the credential been backed up to the platform's sync fabric
    # (iCloud Keychain, Google Password Manager, etc.)? Useful in the UI.
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Transports the authenticator advertised — JSON list of strings
    # like ["internal"], ["usb"], ["nfc", "ble"]. Lets the client build
    # the right allowCredentials hint on assertion-begin.
    transports: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # User-supplied nickname. Helps the user pick which key to revoke.
    nickname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebAuthnChallenge(IdMixin, TenantMixin, TimestampMixin, Base):
    """Short-lived challenges stored between *-begin and *-finish.

    WebAuthn is a two-step ceremony: the server hands the browser a
    random challenge, the browser asks the authenticator to sign it,
    and the server verifies the signature is over the same challenge.
    The challenge has to be stored server-side between the two HTTP
    requests — that's this table.

    ``purpose`` distinguishes the two ceremonies (registration vs
    authentication) so a registration challenge can't be repurposed as
    an authentication challenge.

    ``user_id`` is nullable: authenticate-begin doesn't always know the
    user (e.g. passkey discoverable credentials) — we look it up after
    the assertion comes back.

    Tenant-scoped so concurrent ceremonies in different tenants can't
    cross-pollinate.
    """
    __tablename__ = "webauthn_challenges"

    user_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)  # "register" | "authenticate"
    challenge: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
