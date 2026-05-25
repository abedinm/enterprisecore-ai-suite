"""Device-bound refresh tokens.

Adds four columns to ``refresh_tokens`` so we can:

* Reject a refresh-token replay from a different device fingerprint
  (UA + IP-network bucket hash) than the one it was issued to. A leaked
  token is no longer enough — the attacker also needs to come from the
  same browser AND the same /24.
* Show users a "Sessions" list in Settings with a friendly device label
  ("Chrome on Windows from 203.0.113.0/24"), last-used timestamp, and a
  revoke button.

All columns are nullable for backward-compatibility — refresh tokens
issued before this migration won't carry a fingerprint, and the
verification path treats a NULL fingerprint as "skip the check on this
legacy row" (it will be backfilled on the next refresh).

Idempotent: every column add is gated by an inspector lookup so the
migration is safe to re-run against a DB built via
``Base.metadata.create_all`` (the pattern the test suite uses).

Revision ID: 0027_refresh_token_device
Revises:     0026_webauthn
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_refresh_token_device"
down_revision: str | None = "0026_webauthn"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in set(insp.get_table_names()):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _existing_columns("refresh_tokens")
    if not cols:
        # Table doesn't exist yet (fresh test DB built only with
        # Base.metadata.create_all up to an older head — should never happen
        # in CI but handled defensively).
        return
    with op.batch_alter_table("refresh_tokens") as batch:
        if "device_fingerprint" not in cols:
            batch.add_column(sa.Column("device_fingerprint", sa.String(length=64), nullable=True))
        if "device_label" not in cols:
            batch.add_column(sa.Column("device_label", sa.String(length=120), nullable=True))
        if "last_used_at" not in cols:
            batch.add_column(sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
        if "last_used_ip" not in cols:
            batch.add_column(sa.Column("last_used_ip", sa.String(length=64), nullable=True))
    # Index on device_fingerprint for fast "list my sessions" queries.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_ix = {ix["name"] for ix in insp.get_indexes("refresh_tokens")}
    if "ix_refresh_tokens_device_fingerprint" not in existing_ix:
        op.create_index(
            "ix_refresh_tokens_device_fingerprint",
            "refresh_tokens",
            ["device_fingerprint"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "refresh_tokens" not in set(insp.get_table_names()):
        return
    existing_ix = {ix["name"] for ix in insp.get_indexes("refresh_tokens")}
    if "ix_refresh_tokens_device_fingerprint" in existing_ix:
        op.drop_index("ix_refresh_tokens_device_fingerprint", table_name="refresh_tokens")
    cols = _existing_columns("refresh_tokens")
    with op.batch_alter_table("refresh_tokens") as batch:
        for c in ("last_used_ip", "last_used_at", "device_label", "device_fingerprint"):
            if c in cols:
                batch.drop_column(c)
