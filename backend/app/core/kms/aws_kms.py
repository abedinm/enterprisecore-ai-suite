"""AWS KMS BYOK provider.

Wraps a DEK with the customer's AWS KMS Customer Master Key (CMK). The
``key_ref`` is the CMK's ARN — ``arn:aws:kms:us-east-1:111122223333:key/...``.

Requires ``boto3``. Pulled in by ``requirements-byok.txt``.
"""
from __future__ import annotations

try:
    import boto3  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError("boto3 is required for AWS KMS BYOK") from exc


def _client():
    return boto3.client("kms")


def wrap(plaintext_dek: bytes, key_ref: str) -> bytes:
    resp = _client().encrypt(KeyId=key_ref, Plaintext=plaintext_dek)
    return resp["CiphertextBlob"]


def unwrap(wrapped_dek: bytes, key_ref: str) -> bytes:
    resp = _client().decrypt(CiphertextBlob=wrapped_dek, KeyId=key_ref)
    return resp["Plaintext"]
