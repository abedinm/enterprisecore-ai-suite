"""KMS provider stubs for BYOK envelope encryption.

Each submodule (``aws_kms``, ``gcp_kms``, ``azure_kv``, ``hcv_transit``)
exposes two top-level callables::

    wrap(plaintext_dek: bytes, key_ref: str) -> bytes
    unwrap(wrapped_dek: bytes, key_ref: str) -> bytes

They are intentionally optional: importing one without its backing
cloud SDK installed raises ``ImportError`` and
:func:`app.core.encryption._kms_provider` logs a warning + falls back to
the server-managed wrapping. Customers who want true BYOK install
``requirements-byok.txt`` to pull the corresponding SDK.
"""
