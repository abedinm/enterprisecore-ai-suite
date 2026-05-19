"""Rename naive-pluralizer tables to proper English plurals.

The base class used ``cls.__name__.lower() + 's'`` which gave us
``expense_categorys``, ``journal_entrys`` and friends. The improved pluralizer
now produces ``expense_categories`` etc. — but anyone whose DB was created
before this migration still has the ugly names. This migration renames them
in place.

Revision ID: 0002_rename_pluralized
Revises: 0001_initial
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision: str = "0002_rename_pluralized"
down_revision: str | None = "0001_initial"
branch_labels: str | None = None
depends_on: str | None = None


# (old_name, new_name) — applied in order. Reversed on downgrade.
RENAMES: list[tuple[str, str]] = [
    ("expense_categorys", "expense_categories"),
    ("journal_entrys", "journal_entries"),
    ("time_entrys", "time_entries"),
    ("password_vault_entrys", "password_vault_entries"),
    ("communication_entrys", "communication_entries"),
    ("search_indexs", "search_indexes"),
    ("search_historys", "search_histories"),
    ("product_categorys", "product_categories"),
    ("task_dependencys", "task_dependencies"),
]


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()
    for old, new in RENAMES:
        if old in existing and new not in existing:
            op.rename_table(old, new)


def downgrade() -> None:
    existing = _existing_tables()
    for old, new in RENAMES:
        if new in existing and old not in existing:
            op.rename_table(new, old)
