"""Azure Key Vault BYOK provider.

``key_ref`` is the key identifier URL ``https://<vault>.vault.azure.net/keys/<name>/<version>``.
Requires ``azure-keyvault-keys`` + ``azure-identity``.
"""
from __future__ import annotations

try:
    from azure.identity import DefaultAzureCredential  # type: ignore
    from azure.keyvault.keys.crypto import (  # type: ignore
        CryptographyClient, EncryptionAlgorithm,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "azure-keyvault-keys + azure-identity are required for Azure Key Vault BYOK"
    ) from exc


def _client(key_ref: str) -> "CryptographyClient":
    return CryptographyClient(key_ref, credential=DefaultAzureCredential())


def wrap(plaintext_dek: bytes, key_ref: str) -> bytes:
    client = _client(key_ref)
    result = client.encrypt(EncryptionAlgorithm.rsa_oaep_256, plaintext_dek)
    return result.ciphertext


def unwrap(wrapped_dek: bytes, key_ref: str) -> bytes:
    client = _client(key_ref)
    result = client.decrypt(EncryptionAlgorithm.rsa_oaep_256, wrapped_dek)
    return result.plaintext
