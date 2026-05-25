"""GCP KMS BYOK provider.

Wraps a DEK with a CryptoKey in Google Cloud KMS. ``key_ref`` is the
fully-qualified resource name:
``projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>``.

Requires ``google-cloud-kms`` (pulled in via ``requirements-byok.txt``).
"""
from __future__ import annotations

try:
    from google.cloud import kms  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError("google-cloud-kms is required for GCP KMS BYOK") from exc


def _client():
    return kms.KeyManagementServiceClient()


def wrap(plaintext_dek: bytes, key_ref: str) -> bytes:
    client = _client()
    resp = client.encrypt(request={"name": key_ref, "plaintext": plaintext_dek})
    return resp.ciphertext


def unwrap(wrapped_dek: bytes, key_ref: str) -> bytes:
    client = _client()
    resp = client.decrypt(request={"name": key_ref, "ciphertext": wrapped_dek})
    return resp.plaintext
