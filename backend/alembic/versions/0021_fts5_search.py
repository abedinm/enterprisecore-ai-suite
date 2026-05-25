"""FTS5 cross-module search index.

Creates the ``search_index_fts`` SQLite FTS5 virtual table — the backing
store for the global search bar. The table is a denormalised mirror of
searchable rows across the suite; the application layer keeps it in sync
through SQLAlchemy ``after_insert``/``after_update``/``after_delete``
event listeners (see ``app/services/search.py``).

Idempotent: if the table already exists (fresh test DB built via
``Base.metadata.create_all`` — the DDL hook in
``app/models/search_index.py`` fires there and produces the same table)
this migration is a no-op.

Skipped on non-SQLite backends. Postgres deployments should use
``pg_trgm`` / ``tsvector`` instead and will get their own migration in a
future phase. Skipping here keeps the alembic upgrade path clean for
mixed test environments without forcing every Postgres dev to install
the FTS5 SQLite extension.

Revision ID: 0021_fts5_search
Revises: 0020_marketing_settings_id
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0021_fts5_search"
down_revision: str | None = "0020_marketing_settings_id"
branch_labels: str | None = None
depends_on: str | None = None


_FTS5_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_index_fts USING fts5(
    entity_type UNINDEXED,
    entity_id UNINDEXED,
    tenant_id UNINDEXED,
    title,
    subtitle,
    body,
    tokenize = 'porter unicode61 remove_diacritics 2'
)
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        # Non-SQLite backends use a different full-text approach; nothing to do
        # in this migration. See module docstring.
        return
    # IF NOT EXISTS makes this safe to re-run on a DB that already had the
    # virtual table created via Base.metadata.create_all.
    op.execute(sa.text(_FTS5_DDL))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    op.execute(sa.text("DROP TABLE IF EXISTS search_index_fts"))
