# WebAuthn Passkeys

EnterpriseCore ships first-class WebAuthn / FIDO2 passkey support for
phishing-resistant 2FA and passwordless sign-in. Customers can register
hardware keys (YubiKey), platform authenticators (Touch ID, Windows
Hello, Face ID), and password-manager passkeys (1Password, iCloud
Keychain, Google Password Manager) — every credential lives on the same
``webauthn_credentials`` table, scoped to the tenant.

This document covers operator configuration and the API surface. The
WebAuthn spec is the canonical reference for ceremony details.

## Why passkeys

A password + TOTP code can be phished — the user is tricked into
entering both into a lookalike site. WebAuthn binds the credential to
the relying-party origin at the authenticator level, so a passkey
registered for ``app.enterprisecore.com`` cannot be used on
``app.enterpr1secore.com``. There's no shared secret to leak.

Common deployments:

* **2FA** — keep password login, add a passkey as the second factor.
* **Passwordless** — register a passkey, then sign in via the passkey
  flow without ever typing a password.

EnterpriseCore supports both. The endpoint that mints tokens on
successful assertion is independent of the password endpoint, so a
tenant can disable password auth entirely and require passkeys.

## Configuration

Three environment variables configure the Relying Party identity. The
defaults are placeholders — every production deploy MUST override them.

| Variable             | Purpose                                                          | Default                                |
|----------------------|------------------------------------------------------------------|----------------------------------------|
| ``WEBAUTHN_RP_ID``   | The "relying party id" — the hostname passkeys are bound to.     | ``enterprisecore.local``               |
| ``WEBAUTHN_RP_NAME`` | Human-readable name shown in browser passkey prompts.            | ``EnterpriseCore``                     |
| ``WEBAUTHN_ORIGIN``  | The full origin the SPA serves from (used for origin checking).  | ``https://app.enterprisecore.local``   |

``WEBAUTHN_RP_ID`` MUST be either an exact match to the origin's host
or a registrable suffix of it. For a SPA at ``https://app.acme.com``
either ``app.acme.com`` or ``acme.com`` is valid; ``other.com`` is not.

## API surface

All routes live under ``/api/v1/webauthn``.

### Registration (auth required)

```
POST /api/v1/webauthn/register/begin
```
Returns ``PublicKeyCredentialCreationOptions`` for the current user.
The browser feeds this into ``navigator.credentials.create({publicKey})``.

```
POST /api/v1/webauthn/register/finish
Body: { "credential": <PublicKeyCredential>, "nickname": "MacBook Touch ID" }
```
Verifies the attestation and persists a credential row. ``nickname`` is
optional but recommended — it's what users see when they revoke an old
key.

### Authentication (public)

```
POST /api/v1/webauthn/authenticate/begin
Body: { "email": "ada@acme.com" }
```
Always returns options — even for unknown emails — so the endpoint
can't be used for account enumeration.

```
POST /api/v1/webauthn/authenticate/finish
Body: { "email": "ada@acme.com", "credential": <PublicKeyCredential> }
```
Verifies the assertion. On success, mints an access + refresh JWT pair
identical to the password login endpoint and sets httpOnly auth
cookies.

### Credential management (auth required)

```
GET    /api/v1/webauthn/credentials
DELETE /api/v1/webauthn/credentials/{id}
```

## Replay protection

Every authenticator advertises a monotonically-increasing sign counter
in the assertion response. We persist the latest value on
``WebAuthnCredential.sign_count`` and reject any assertion whose
counter is less-than-or-equal to what's on file — the canonical replay
defence baked into the WebAuthn spec.

Some authenticators (notably platform passkeys on iCloud Keychain
since iOS 17) don't implement the counter — they always send 0. In
that case we accept the assertion but log a single warning event per
credential so operators can see which authenticators don't advance.

## Cross-tenant isolation

Credentials are tenant-scoped via ``tenant_id``. A passkey registered
under Tenant A cannot be used to sign in as the same email under
Tenant B — the authenticate-finish endpoint rejects with 401 if the
credential's user tenant differs from the request tenant. This is the
canonical defence against a customer running multiple isolated tenants
in the same install (acquisition holdcos, multi-brand orgs).

## Library

Server-side verification uses the canonical
[``webauthn``](https://pypi.org/project/webauthn/) package (Duo Labs).
It's pure Python — no native build, no system libs. The dep is pinned
in ``requirements.txt`` at ``webauthn>=2.0,<3.0``.

## What's NOT in scope here

* The browser-side UI (the SPA agent owns ``navigator.credentials``
  calls + the registration flow UX).
* Migration tooling for users with an existing password — they can add
  a passkey alongside their password from the security settings page
  and the next login attempt will offer either option.
