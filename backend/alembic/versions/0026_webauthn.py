"""WebAuthn passkey credentials + challenge ledger.

Two tables back the FIDO2 / WebAuthn passkey ceremonies:

* ``webauthn_credentials`` — one row per registered authenticator
  (security key, Touch ID, Windows Hello, password-manager passkey).
  Holds the credential id, COSE public key, rolling sign counter, and
  user-friendly metadata (nickname, transports, AAGUID).
* ``webauthn_challenges`` — short-lived challenges stored between the
  ``*/begin`` and ``*/finish`` endpoints. Tenant-scoped so concurrent
  ceremonies in different tenants can't cross-pollinate.

Both are tenant-scoped via ``tenant_id`` (CASCADE on ``tenants.id``)
so wiping a tenant cleanly removes its passkeys.

Idempotent: each ``create_table`` is gated by ``_has_table`` so the
migration is safe to re-run against a DB built via
``Base.metadata.create_all`` (the pattern the test suite uses).

Revision ID: 0025_webauthn
Revises: 0025_realtime  (the realtime migration is the previous head; the
                         intended chain is perf_indexes → realtime →
                         webauthn). The original reference to "0024_realtime"
                         was a typo — there is no 0024_realtime revision in
                         the tree, only 0025_realtime + 0024_perf_indexes.
Create Date: 2026-05-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0026_webauthn"
down_revision: str | None = "0025_realtime"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("webauthn_credentials"):
        op.create_table(
            "webauthn_credentials",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "user_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                index=True, nullable=False,
            ),
            sa.Column("credential_id", sa.LargeBinary, nullable=False, unique=True, index=True),
            sa.Column("public_key", sa.LargeBinary, nullable=False),
            sa.Column("sign_count", sa.Integer, server_default="0", nullable=False),
            sa.Column("aaguid", sa.LargeBinary, nullable=True),
            sa.Column("backed_up", sa.Boolean, server_default=sa.text("0"), nullable=False),
            sa.Column("transports", sa.JSON, server_default=sa.text("'[]'"), nullable=False),
            sa.Column("nickname", sa.String(length=120), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("webauthn_challenges"):
        op.create_table(
            "webauthn_challenges",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "user_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                index=True, nullable=True,
            ),
            sa.Column("email", sa.String(length=255), index=True, nullable=True),
            sa.Column("purpose", sa.String(length=20), nullable=False),
            sa.Column("challenge", sa.LargeBinary, nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for tbl in ("webauthn_challenges", "webauthn_credentials"):
        if _has_table(tbl):
            op.drop_table(tbl)
