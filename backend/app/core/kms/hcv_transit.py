"""HashiCorp Vault Transit BYOK provider.

``key_ref`` is the transit key name (e.g. ``enterprisecore-dek``). The
Vault address + token are read from environment variables
``VAULT_ADDR`` / ``VAULT_TOKEN`` per hvac convention.

Requires ``hvac``.
"""
from __future__ import annotations

import base64
import os

try:
    import hvac  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError("hvac is required for HashiCorp Vault transit BYOK") from exc


def _client():
    return hvac.Client(
        url=os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200"),
        token=os.environ.get("VAULT_TOKEN", ""),
    )


def wrap(plaintext_dek: bytes, key_ref: str) -> bytes:
    client = _client()
    resp = client.secrets.transit.encrypt_data(
        name=key_ref,
        plaintext=base64.b64encode(plaintext_dek).decode("ascii"),
    )
    return resp["data"]["ciphertext"].encode("ascii")


def unwrap(wrapped_dek: bytes, key_ref: str) -> bytes:
    client = _client()
    resp = client.secrets.transit.decrypt_data(
        name=key_ref,
        ciphertext=wrapped_dek.decode("ascii"),
    )
    return base64.b64decode(resp["data"]["plaintext"])
