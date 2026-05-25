"""Migrate bots, conversations, and chat messages out of a standalone LinguaBot
SQLite database into the EnterpriseCore Web Chat Widget module.

LinguaBot was absorbed into EnterpriseCore during Phase 1 of the consolidation,
so existing LinguaBot operators need a one-shot import path. This script reads
the source DB with raw ``sqlite3`` (no LinguaBot models in the venv) and writes
into EnterpriseCore's webchat.* tables via the ORM.

LinguaBot source schema (inspected against
``F:/LinguaBot/backend/linguabot.db``):

    users        (id INT pk, email, password_hash, created_at)
    bots         (id INT pk, public_id, owner_id FK users.id,
                  name, welcome_message, supported_languages CSV,
                  business_info, encrypted_api_key, accent_color,
                  created_at, updated_at)
    conversations(id INT pk, bot_id FK bots.id, session_id, language,
                  created_at, last_message_at)
    messages     (id INT pk, conversation_id FK conversations.id,
                  role, content, language, created_at)

Field mapping into EnterpriseCore webchat.*:

    Bot.name              <- bots.name
    Bot.description       <- bots.business_info (truncated to a sensible blurb)
    Bot.language_preset   <- derived from bots.supported_languages
                             (single-locale → that locale, else "auto")
    Bot.system_prompt     <- bots.welcome_message
                             (LinguaBot had no system_prompt; the welcome
                             string is the closest 1:1 carry-over)
    Bot.model             <- left at EnterpriseCore default (claude-haiku-4-5)
    Bot.provider          <- "anthropic"
    Bot.api_key_encrypted <- skipped (different Fernet keys; user re-enters
                             their BYO key in the EnterpriseCore Studio).

    Conversation.visitor_session_id <- conversations.session_id
    Conversation.started_at         <- conversations.created_at
    Conversation.last_message_at    <- conversations.last_message_at
    Conversation.contact_id         <- null (CRM linking is opt-in)

    ChatMessage.role / content / created_at carry over verbatim. tokens_in /
    tokens_out / cost_usd default to 0 — LinguaBot didn't record usage stats.
    language_detected <- messages.language.

Usage::

    python scripts/migrate_from_linguabot.py \\
        --source F:/LinguaBot/backend/linguabot.db \\
        --owner-email admin@local \\
        [--dry-run]

Idempotency: a Bot is skipped if (owner_id, name) already exists in the
destination. Conversations are deduped by (bot_id, visitor_session_id). Within
an already-imported conversation, messages are deduped by (role, content,
created_at) — coarse but effective for LinguaBot data (no per-message UUIDs).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

# Allow the script to be run as ``python scripts/migrate_from_linguabot.py``.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.webchat import Bot, ChatMessage, Conversation  # noqa: E402


SUPPORTED_LOCALES = {"en", "bn", "hi", "ur"}


@dataclass
class MigrationReport:
    """Counts emitted at the end of a migration run."""

    bots_imported: int = 0
    bots_skipped: int = 0
    conversations_imported: int = 0
    conversations_skipped: int = 0
    messages_imported: int = 0
    messages_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Imported {self.bots_imported} bots, "
            f"{self.conversations_imported} conversations, "
            f"{self.messages_imported} messages. "
            f"Skipped {self.bots_skipped + self.conversations_skipped + self.messages_skipped} "
            f"duplicates "
            f"({self.bots_skipped} bots, {self.conversations_skipped} conversations, "
            f"{self.messages_skipped} messages)."
        )


def _parse_ts(value) -> datetime | None:
    """LinguaBot stores DATETIME as text; SQLAlchemy's SQLite DateTime column on
    the destination expects a Python ``datetime``. Parse whichever flavour we
    find and assume UTC if the timestamp is naive."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    # Common SQLite text formats: ISO 8601, with or without "T", with or
    # without microseconds, with or without timezone.
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Last resort: fromisoformat handles a wide variety including offsets.
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Could not parse timestamp {!r}; using now()", text)
        return datetime.now(timezone.utc)


def _derive_language_preset(supported_csv: str | None) -> str:
    """LinguaBot stores supported languages as ``en,bn,hi,ur``. EnterpriseCore's
    Bot.language_preset is a single value (``auto`` or one of en/bn/hi/ur). If
    the LinguaBot bot only supported one language, prefer that; otherwise
    ``auto`` lets the visitor's message drive the response language."""
    if not supported_csv:
        return "auto"
    parts = [p.strip().lower() for p in supported_csv.split(",") if p.strip()]
    valid = [p for p in parts if p in SUPPORTED_LOCALES]
    if len(valid) == 1:
        return valid[0]
    return "auto"


def _open_source(source_path: Path) -> sqlite3.Connection:
    """Open the LinguaBot SQLite read-only and return a cursor-friendly conn."""
    conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_owner(db: Session, owner_email: str) -> User:
    user = db.scalar(select(User).where(User.email == owner_email.lower()))
    if not user:
        raise LookupError(f"No EnterpriseCore user with email {owner_email!r}")
    return user


def _existing_bot_names(db: Session, owner_id: str) -> set[str]:
    rows = db.scalars(select(Bot.name).where(Bot.owner_id == owner_id)).all()
    return set(rows)


def _existing_session_ids(db: Session, bot_id: str) -> set[str]:
    rows = db.scalars(
        select(Conversation.visitor_session_id).where(Conversation.bot_id == bot_id)
    ).all()
    return set(rows)


def _existing_message_keys(db: Session, conversation_id: str) -> set[tuple[str, str, datetime]]:
    rows = db.execute(
        select(ChatMessage.role, ChatMessage.content, ChatMessage.created_at).where(
            ChatMessage.conversation_id == conversation_id
        )
    ).all()
    out: set[tuple[str, str, datetime]] = set()
    for role, content, created_at in rows:
        if isinstance(created_at, datetime) and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        out.add((role, content, created_at))
    return out


def _iter_rows(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> Iterable[sqlite3.Row]:
    cur = conn.execute(sql, tuple(params))
    try:
        while True:
            row = cur.fetchone()
            if row is None:
                break
            yield row
    finally:
        cur.close()


def migrate(
    source_path: Path,
    owner_email: str,
    *,
    db: Session,
    dry_run: bool = False,
) -> MigrationReport:
    """Run the migration. Caller owns the session lifecycle (so tests can pass
    in an isolated session). Commits at the end on success; rolls back on
    failure or ``dry_run``."""
    report = MigrationReport()

    if not source_path.exists():
        raise FileNotFoundError(f"Source LinguaBot DB not found: {source_path}")

    owner = _resolve_owner(db, owner_email)
    logger.info(
        "Importing into EnterpriseCore as owner {} ({}); dry_run={}",
        owner.email, owner.id, dry_run,
    )

    src = _open_source(source_path)
    try:
        existing_names = _existing_bot_names(db, owner.id)

        # bot.id (LinguaBot int) -> Bot.id (EnterpriseCore ULID), so child rows
        # can FK to the right destination bot.
        bot_id_map: dict[int, str] = {}

        for row in _iter_rows(src, "SELECT * FROM bots"):
            if row["name"] in existing_names:
                logger.info("Skip bot {!r} — already exists for owner", row["name"])
                report.bots_skipped += 1
                # Look up the existing destination bot so we still copy its
                # conversations/messages on this run. (Without this, idempotent
                # re-runs would never finish an interrupted import.)
                existing_bot = db.scalar(
                    select(Bot).where(Bot.owner_id == owner.id, Bot.name == row["name"])
                )
                if existing_bot:
                    bot_id_map[row["id"]] = existing_bot.id
                continue
            bot = Bot(
                owner_id=owner.id,
                name=row["name"],
                description=(row["business_info"] or "")[:1000] or None,
                language_preset=_derive_language_preset(row["supported_languages"]),
                system_prompt=row["welcome_message"] or "",
                # Keep destination defaults — LinguaBot didn't store these.
                model="claude-haiku-4-5-20251001",
                provider="anthropic",
                is_public=True,
                api_key_encrypted=None,
                rate_limit_per_min=20,
            )
            db.add(bot)
            db.flush()  # populate bot.id
            bot_id_map[row["id"]] = bot.id
            report.bots_imported += 1
            logger.info("Imported bot {!r} -> {}", row["name"], bot.id)
            existing_names.add(row["name"])

        # Conversations
        # conv.id (LinguaBot int) -> Conversation.id (ULID)
        conv_id_map: dict[int, str] = {}
        for row in _iter_rows(src, "SELECT * FROM conversations"):
            dest_bot_id = bot_id_map.get(row["bot_id"])
            if not dest_bot_id:
                # Orphaned conversation (its bot wasn't imported because the
                # source row was somehow missing). Skip quietly.
                continue
            existing_sessions = _existing_session_ids(db, dest_bot_id)
            if row["session_id"] in existing_sessions:
                report.conversations_skipped += 1
                # Locate the existing destination conversation so messages can
                # still be appended on a re-run.
                existing_conv = db.scalar(
                    select(Conversation).where(
                        Conversation.bot_id == dest_bot_id,
                        Conversation.visitor_session_id == row["session_id"],
                    )
                )
                if existing_conv:
                    conv_id_map[row["id"]] = existing_conv.id
                continue
            started_at = _parse_ts(row["created_at"]) or datetime.now(timezone.utc)
            last_msg_at = (
                _parse_ts(row["last_message_at"])
                or _parse_ts(row["created_at"])
                or started_at
            )
            conv = Conversation(
                bot_id=dest_bot_id,
                contact_id=None,
                visitor_session_id=row["session_id"],
                visitor_locale_hint=row["language"],
                started_at=started_at,
                last_message_at=last_msg_at,
            )
            db.add(conv)
            db.flush()
            conv_id_map[row["id"]] = conv.id
            report.conversations_imported += 1

        # Messages — dedup by (role, content, parsed-timestamp) so re-running
        # the import after a partial run doesn't double-insert. We compare on
        # the parsed datetime (not raw text) because the destination table
        # round-trips through SQLAlchemy DateTime.
        for row in _iter_rows(src, "SELECT * FROM messages ORDER BY id"):
            dest_conv_id = conv_id_map.get(row["conversation_id"])
            if not dest_conv_id:
                continue
            existing_keys = _existing_message_keys(db, dest_conv_id)
            created_at = _parse_ts(row["created_at"]) or datetime.now(timezone.utc)
            key = (row["role"], row["content"], created_at)
            if key in existing_keys:
                report.messages_skipped += 1
                continue
            msg = ChatMessage(
                conversation_id=dest_conv_id,
                role=row["role"],
                content=row["content"],
                tokens_in=0,
                tokens_out=0,
                language_detected=row["language"],
                latency_ms=0,
                created_at=created_at,
            )
            db.add(msg)
            report.messages_imported += 1

        if dry_run:
            logger.info("Dry run — rolling back; no data was written.")
            db.rollback()
        else:
            db.commit()
            logger.info("Commit complete.")
    except Exception as exc:
        db.rollback()
        report.errors.append(str(exc))
        raise
    finally:
        src.close()

    return report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="migrate_from_linguabot",
        description=(
            "Import LinguaBot bots/conversations/messages into "
            "EnterpriseCore's Web Chat Widget module."
        ),
    )
    p.add_argument("--source", required=True, help="Path to the LinguaBot SQLite file")
    p.add_argument(
        "--owner-email",
        required=True,
        help="Email of an existing EnterpriseCore user who will own the imported bots",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be imported without writing anything",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    source = Path(args.source).expanduser().resolve()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{level}</level> | {message}")

    db = SessionLocal()
    try:
        report = migrate(
            source_path=source,
            owner_email=args.owner_email,
            db=db,
            dry_run=args.dry_run,
        )
        print(report.summary())
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except LookupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
