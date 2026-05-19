"""AI Coding Assistant module — full schema for 15 tools.

Adds the two new tables (``regex_library_entries``, ``database_connections``)
and brings the existing coding/ai tables in sync with the rebuilt ORM models
(BYO-key fields on usage, multi-file chat bookkeeping, snippet metadata,
saved Postman-style requests, Chatbot extensions, etc.).

The migration is idempotent: it inspects the live database first and only
applies the deltas that haven't been applied yet. That makes it safe to run
on a fresh install (where 0001 already created the latest snapshot) and on
an upgraded install (where the old, leaner shape is still in place).

Revision ID: 0003_ai_coding_module
Revises: 0002_rename_pluralized
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ai_coding_module"
down_revision: str | None = "0002_rename_pluralized"
branch_labels: str | None = None
depends_on: str | None = None


# ---- Idempotent helpers -------------------------------------------------
def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _add_column(table: str, column: sa.Column) -> None:
    if _has_table(table) and not _has_column(table, column.name):
        with op.batch_alter_table(table) as batch:
            batch.add_column(column)


def _drop_column(table: str, column: str) -> None:
    if _has_table(table) and _has_column(table, column):
        with op.batch_alter_table(table) as batch:
            batch.drop_column(column)


# ---- Upgrade ------------------------------------------------------------
def upgrade() -> None:
    # --- New tables -----------------------------------------------------
    if not _has_table("regex_library_entries"):
        op.create_table(
            "regex_library_entries",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False, index=True),
            sa.Column("pattern", sa.Text, nullable=False),
            sa.Column("flags", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("description", sa.Text),
            sa.Column("explanation", sa.Text),
            sa.Column("owner_id", sa.String(length=32),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("database_connections"):
        op.create_table(
            "database_connections",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False, index=True),
            sa.Column("dialect", sa.String(length=40), nullable=False),
            sa.Column("dsn_encrypted", sa.Text, nullable=False),
            sa.Column("owner_id", sa.String(length=32),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # --- code_projects: legacy schema used root_path/language ----------
    if _has_table("code_projects"):
        _add_column("code_projects",
                    sa.Column("path", sa.String(length=500), nullable=True))
        _add_column("code_projects",
                    sa.Column("description", sa.Text, nullable=True))
        _add_column("code_projects",
                    sa.Column("language_primary", sa.String(length=40), nullable=True))
        _add_column("code_projects",
                    sa.Column("is_git", sa.Boolean, server_default=sa.text("0"), nullable=False))
        if _has_column("code_projects", "root_path") and _has_column("code_projects", "path"):
            op.execute("UPDATE code_projects SET path = root_path WHERE path IS NULL")
            _drop_column("code_projects", "root_path")
        if _has_column("code_projects", "language") and _has_column("code_projects", "language_primary"):
            op.execute("UPDATE code_projects SET language_primary = language WHERE language_primary IS NULL")
            _drop_column("code_projects", "language")

    # --- code_snippets ---------------------------------------------------
    _add_column("code_snippets", sa.Column("description", sa.Text, nullable=True))
    _add_column("code_snippets",
                sa.Column("is_public", sa.Boolean, server_default=sa.text("0"), nullable=False))
    _add_column("code_snippets",
                sa.Column("use_count", sa.Integer, server_default="0", nullable=False))
    # The old `tags TEXT default '[]'` and the new `tags JSON` are compatible
    # at the storage layer (JSON falls back to TEXT on SQLite), so no migration
    # is needed for that column.

    # --- api_requests ---------------------------------------------------
    if _has_table("api_requests"):
        _add_column("api_requests", sa.Column("params", sa.JSON, nullable=True))
        _add_column("api_requests",
                    sa.Column("collection", sa.String(length=120), nullable=True, index=True))
        _add_column("api_requests", sa.Column("owner_id", sa.String(length=32), nullable=True))

    # --- ai_conversations ----------------------------------------------
    _add_column("ai_conversations", sa.Column("model", sa.String(length=120), nullable=True))

    # --- ai_messages ----------------------------------------------------
    _add_column("ai_messages",
                sa.Column("tokens_in", sa.Integer, server_default="0", nullable=False))
    _add_column("ai_messages",
                sa.Column("tokens_out", sa.Integer, server_default="0", nullable=False))
    if _has_column("ai_messages", "token_count"):
        # Best-effort migration of old token_count → tokens_out (the larger of the two,
        # since it usually counts the assistant turn).
        op.execute("UPDATE ai_messages SET tokens_out = token_count "
                   "WHERE token_count IS NOT NULL AND tokens_out = 0")
        _drop_column("ai_messages", "token_count")

    # --- ai_usage_records ----------------------------------------------
    if _has_table("ai_usage_records"):
        _add_column("ai_usage_records",
                    sa.Column("feature", sa.String(length=80),
                              server_default="general", nullable=False))
        _add_column("ai_usage_records",
                    sa.Column("latency_ms", sa.Integer, server_default="0", nullable=False))
        _add_column("ai_usage_records",
                    sa.Column("success", sa.Boolean, server_default=sa.text("1"), nullable=False))
        _add_column("ai_usage_records",
                    sa.Column("occurred_at", sa.DateTime(timezone=True),
                              server_default=sa.func.now(), nullable=False))
        _add_column("ai_usage_records",
                    sa.Column("tokens_in", sa.Integer, server_default="0", nullable=False))
        _add_column("ai_usage_records",
                    sa.Column("tokens_out", sa.Integer, server_default="0", nullable=False))
        if _has_column("ai_usage_records", "input_tokens"):
            op.execute("UPDATE ai_usage_records SET tokens_in = input_tokens "
                       "WHERE input_tokens IS NOT NULL")
            _drop_column("ai_usage_records", "input_tokens")
        if _has_column("ai_usage_records", "output_tokens"):
            op.execute("UPDATE ai_usage_records SET tokens_out = output_tokens "
                       "WHERE output_tokens IS NOT NULL")
            _drop_column("ai_usage_records", "output_tokens")

    # --- chatbots -------------------------------------------------------
    if _has_table("chatbots"):
        _add_column("chatbots", sa.Column("description", sa.Text, nullable=True))
        _add_column("chatbots",
                    sa.Column("system_prompt", sa.Text, server_default="", nullable=False))
        _add_column("chatbots", sa.Column("welcome_message", sa.Text, nullable=True))
        _add_column("chatbots",
                    sa.Column("provider", sa.String(length=40),
                              server_default="anthropic", nullable=False))
        _add_column("chatbots", sa.Column("model", sa.String(length=120), nullable=True))
        _add_column("chatbots",
                    sa.Column("temperature", sa.Numeric(4, 3),
                              server_default="0.700", nullable=False))
        _add_column("chatbots",
                    sa.Column("is_active", sa.Boolean,
                              server_default=sa.text("1"), nullable=False))
        _add_column("chatbots", sa.Column("public_token", sa.String(length=64), nullable=True))
        if _has_column("chatbots", "instructions"):
            op.execute("UPDATE chatbots SET system_prompt = instructions "
                       "WHERE (system_prompt IS NULL OR system_prompt = '')")
            _drop_column("chatbots", "instructions")
        if _has_column("chatbots", "knowledge_sources"):
            _drop_column("chatbots", "knowledge_sources")

    # --- chatbot_messages ----------------------------------------------
    if _has_table("chatbot_messages"):
        _add_column("chatbot_messages",
                    sa.Column("session_id", sa.String(length=64),
                              server_default="default", nullable=False, index=True))


# ---- Downgrade ----------------------------------------------------------
def downgrade() -> None:
    """The downgrade path drops the new tables and the columns added above.
    It does NOT reintroduce the legacy column names — that's intentional: the
    upgrade copies data forward, so going back would lose the bookkeeping
    rather than recover it. If you need to revert, restore from a backup."""
    if _has_table("database_connections"):
        op.drop_table("database_connections")
    if _has_table("regex_library_entries"):
        op.drop_table("regex_library_entries")

    for table, cols in {
        "code_projects": ("description", "language_primary", "is_git"),
        "code_snippets": ("description", "is_public", "use_count"),
        "api_requests": ("params", "collection", "owner_id"),
        "ai_conversations": ("model",),
        "ai_messages": ("tokens_in", "tokens_out"),
        "ai_usage_records": ("feature", "latency_ms", "success", "occurred_at",
                             "tokens_in", "tokens_out"),
        "chatbots": ("description", "system_prompt", "welcome_message", "provider",
                     "model", "temperature", "is_active", "public_token"),
        "chatbot_messages": ("session_id",),
    }.items():
        for c in cols:
            _drop_column(table, c)
