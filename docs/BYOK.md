# Bring Your Own Key (BYOK)

Field-level encryption in EnterpriseCore uses **envelope encryption**:
a 32-byte Data Encryption Key (DEK) protects every encrypted column;
the DEK itself is wrapped by a Master Key. By default the Master Key
is the server's `ENCRYPTION_KEY`. With BYOK the customer points the
suite at a key in their own cloud KMS (or HashiCorp Vault Transit) and
the DEK is wrapped there instead — meaning the customer can revoke
EnterpriseCore's access to their data at any time by disabling the
KMS key.

## How it works

```
   plaintext field
        │  Fernet encrypt with DEK
        ▼
   ciphertext  (stored on the row)
        │
        │  the DEK lives only in process memory
        ▼
   wrapped DEK  (stored on tenant_encryption_keys.wrapped_dek)
        │
        │  unwrap with master key (server) OR with KMS (BYOK)
        ▼
   raw 32-byte DEK
```

Every encrypted field carries a version prefix `v<n>:` so the suite can
read data written under an old DEK while a rotation is in progress.

## Supported KMS providers

| Provider                | `kms_provider` | `kms_key_ref` form                                                       | SDK installed via              |
|-------------------------|----------------|--------------------------------------------------------------------------|--------------------------------|
| Server (default)        | `server`       | (unused)                                                                 | (built-in)                     |
| AWS KMS                 | `aws_kms`      | `arn:aws:kms:us-east-1:111122223333:key/...`                             | `boto3`                        |
| GCP KMS                 | `gcp_kms`      | `projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>`                 | `google-cloud-kms`             |
| Azure Key Vault         | `azure_kv`     | `https://<vault>.vault.azure.net/keys/<name>/<version>`                  | `azure-keyvault-keys`          |
| HashiCorp Vault Transit | `hcv_transit`  | The transit key name (e.g. `enterprisecore-dek`)                         | `hvac`                         |

To enable BYOK in production install the extra requirements:

```bash
pip install -r requirements-byok.txt
```

If the provider's SDK is missing at runtime the suite logs a warning
and **falls back to server-managed wrapping** — it never fails the
request. This means rolling out BYOK can be done dependency-first, then
flipped on per-tenant.

## Switching a tenant to BYOK

1. Provision a key in your cloud KMS. Grant the application's IAM
   principal `Encrypt` + `Decrypt` permissions (`kms:Encrypt`,
   `kms:Decrypt` for AWS; equivalent on GCP/Azure/Vault).
2. As a tenant admin call:

```http
POST /api/v1/encryption/byok
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "kms_provider": "aws_kms",
  "kms_key_ref": "arn:aws:kms:us-east-1:111122223333:key/abcd-..."
}
```

3. The endpoint unwraps the current DEK with the server master key,
   wraps it again under your KMS, persists it as a new key version, and
   marks the previous server-managed version inactive.

## Rotation

```http
POST /api/v1/encryption/rotate
Authorization: Bearer <admin-token>
```

Mints a new DEK at `v(n+1)`, wraps it with the current KMS provider
(server or BYOK — same provider as the current active row), and marks
the old version inactive. The version prefix on each ciphertext lets
the system keep reading old data while a background sweep re-encrypts
under the new DEK.

## Inspecting key state

```http
GET /api/v1/encryption/key    # current active DEK + provider + activation date
GET /api/v1/encryption/keys   # full history of rotations
```

The raw DEK is never returned over the API.

## Cross-tenant isolation

The DEK is keyed by `tenant_id`. Ciphertext encrypted with Tenant A's
DEK cannot be decrypted with Tenant B's DEK — the Fernet token simply
fails the MAC check. Combined with the auto-filter in
`app/core/tenant_orm.py`, this guarantees that even if an operator
accidentally hands a ciphertext from Tenant A to Tenant B's code path,
the decryption raises `ValidationFailed` rather than returning A's
plaintext.

## Sensitive fields under tenant DEK

Today the following columns are encrypted with the per-tenant DEK:

- `audit_stream_destinations.credentials_encrypted` — Splunk HEC
  tokens, Datadog API keys, generic bearer tokens.

Legacy globally-encrypted columns (`webchat_bots.api_key_encrypted`,
`password_vault_entries.encrypted_password`, etc.) continue to be
readable via the legacy path and are eligible for migration to the
per-tenant DEK in a future minor — the encryption module reads both
formats transparently.
