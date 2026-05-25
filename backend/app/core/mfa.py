"""TOTP-based multi-factor authentication.

Secrets are Fernet-encrypted before being written to the ``users.mfa_secret``
column. Verification uses pyotp's default 30-second window with one step of
clock-drift tolerance.
"""
from __future__ import annotations

import secrets
from io import BytesIO

import pyotp

from app.core.config import settings
from app.core.security import decrypt_text, encrypt_text


ISSUER = "EnterpriseCore"


def new_secret() -> str:
    """Generate a fresh base32 TOTP secret."""
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return encrypt_text(secret)


def decrypt_secret(blob: str) -> str:
    return decrypt_text(blob)


def provisioning_uri(secret: str, account_label: str) -> str:
    """otpauth:// URL for an authenticator app to scan."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_label, issuer_name=ISSUER)


def verify(secret_encrypted: str, code: str) -> bool:
    if not secret_encrypted or not code:
        return False
    try:
        secret = decrypt_secret(secret_encrypted)
    except Exception:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def qr_png_b64(uri: str) -> str:
    """Render the otpauth URI as a base64-encoded PNG QR code."""
    import base64

    import qrcode

    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def fresh_backup_codes(n: int = 8) -> list[str]:
    """Generate one-time backup codes (not yet persisted — returned to user once)."""
    return [secrets.token_hex(4).upper() for _ in range(n)]
