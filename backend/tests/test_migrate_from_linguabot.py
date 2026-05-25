"""Tests for scripts/migrate_from_linguabot.py — invoked at the function level
(not the CLI) against a synthetic LinguaBot SQLite file in tmp_path."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.webchat import Bot, ChatMessage, Conversation
from scripts.migrate_from_linguabot import migrate


ADMIN_EMAIL = "admin@local"


def _build_linguabot_db(path: Path) -> None:
    """Build a minimal LinguaBot-shaped SQLite file with 1 bot, 1 conversation,
    2 messages. Schema mirrors what's in F:/LinguaBot/backend/linguabot.db."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id VARCHAR(32) NOT NULL UNIQUE,
            owner_id INTEGER NOT NULL,
            name VARCHAR(120) NOT NULL,
            welcome_message TEXT NOT NULL DEFAULT '',
            supported_languages VARCHAR(64) NOT NULL DEFAULT 'en',
            business_info TEXT NOT NULL DEFAULT '',
            encrypted_api_key TEXT NOT NULL DEFAULT '',
            accent_color VARCHAR(16) NOT NULL DEFAULT '#6366F1',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            session_id VARCHAR(64) NOT NULL,
            language VARCHAR(4) NOT NULL DEFAULT 'en',
            created_at DATETIME NOT NULL,
            last_message_at DATETIME NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role VARCHAR(16) NOT NULL,
            content TEXT NOT NULL,
            language VARCHAR(4) NOT NULL DEFAULT 'en',
            created_at DATETIME NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
        (1, "operator@linguabot.test", "x"),
    )
    conn.execute(
        """INSERT INTO bots (id, public_id, owner_id, name, welcome_message,
                             supported_languages, business_info, encrypted_api_key,
                             accent_color)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            1, "abc123def456", 1, "Bengali Helpdesk",
            "Welcome to our store! Type a question to begin.",
            "en,bn",
            "We sell handmade jute bags shipped from Dhaka.",
            "",
            "#10b981",
        ),
    )
    conn.execute(
        """INSERT INTO conversations (id, bot_id, session_id, language,
                                       created_at, last_message_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (1, 1, "sess-001", "bn", "2026-04-01 10:00:00", "2026-04-01 10:05:00"),
    )
    conn.executemany(
        """INSERT INTO messages (conversation_id, role, content, language, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (1, "user", "Apnara ki Bangla janen?", "bn", "2026-04-01 10:00:30"),
            (1, "assistant", "Hain, ami Bangla janen!", "bn", "2026-04-01 10:00:45"),
        ],
    )
    conn.commit()
    conn.close()


def _owner_id(db, email: str = ADMIN_EMAIL) -> str:
    from app.models.user import User
    return db.scalar(select(User.id).where(User.email == email))


def _imported_bot(db, owner_id: str, name: str) -> Bot | None:
    return db.scalar(
        select(Bot).where(Bot.owner_id == owner_id, Bot.name == name)
    )


def _cleanup(db, owner_id: str, name: str) -> None:
    """Delete any rows left by previous test runs of this module."""
    bot = _imported_bot(db, owner_id, name)
    if bot:
        # Cascades wipe conversations + messages.
        db.delete(bot)
        db.commit()


@pytest.fixture()
def linguabot_db(tmp_path) -> Path:
    p = tmp_path / "linguabot.db"
    _build_linguabot_db(p)
    return p


@pytest.fixture()
def clean(db):
    """Run before + after each test so leftover state never leaks."""
    owner_id = _owner_id(db)
    _cleanup(db, owner_id, "Bengali Helpdesk")
    yield
    _cleanup(db, owner_id, "Bengali Helpdesk")


def test_migrate_happy_path(linguabot_db, db, clean):
    """One bot, one conversation, two messages — all persisted with mapped fields."""
    owner_id = _owner_id(db)
    report = migrate(
        source_path=linguabot_db,
        owner_email=ADMIN_EMAIL,
        db=db,
        dry_run=False,
    )

    assert report.bots_imported == 1
    assert report.conversations_imported == 1
    assert report.messages_imported == 2
    assert report.bots_skipped == 0
    assert report.conversations_skipped == 0
    assert report.messages_skipped == 0

    bot = _imported_bot(db, owner_id, "Bengali Helpdesk")
    assert bot is not None
    assert bot.owner_id == owner_id
    # welcome_message -> system_prompt
    assert bot.system_prompt.startswith("Welcome to our store!")
    # business_info -> description
    assert bot.description and "jute bags" in bot.description
    # supported_languages "en,bn" -> auto (multi-locale)
    assert bot.language_preset == "auto"
    # api_key_encrypted intentionally skipped
    assert bot.api_key_encrypted is None
    assert bot.provider == "anthropic"

    conv = db.scalar(select(Conversation).where(Conversation.bot_id == bot.id))
    assert conv is not None
    assert conv.visitor_session_id == "sess-001"
    assert conv.visitor_locale_hint == "bn"
    assert conv.contact_id is None  # CRM linking opt-in only

    msgs = db.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.created_at)
    ).all()
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert "Apnara ki Bangla" in msgs[0].content
    assert msgs[1].role == "assistant"
    assert msgs[0].language_detected == "bn"


def test_dry_run_writes_nothing(linguabot_db, db, clean):
    owner_id = _owner_id(db)
    report = migrate(
        source_path=linguabot_db,
        owner_email=ADMIN_EMAIL,
        db=db,
        dry_run=True,
    )
    # Counts reflect what *would* have been imported.
    assert report.bots_imported == 1
    assert report.conversations_imported == 1
    assert report.messages_imported == 2

    # Crucially: nothing landed.
    assert _imported_bot(db, owner_id, "Bengali Helpdesk") is None


def test_idempotent_double_run(linguabot_db, db, clean):
    """Running twice doesn't duplicate bots / conversations / messages."""
    owner_id = _owner_id(db)

    first = migrate(source_path=linguabot_db, owner_email=ADMIN_EMAIL, db=db, dry_run=False)
    assert first.bots_imported == 1

    second = migrate(source_path=linguabot_db, owner_email=ADMIN_EMAIL, db=db, dry_run=False)
    # Second run sees existing rows and skips them.
    assert second.bots_imported == 0
    assert second.bots_skipped == 1
    assert second.conversations_imported == 0
    assert second.conversations_skipped == 1
    assert second.messages_imported == 0
    assert second.messages_skipped == 2

    bot = _imported_bot(db, owner_id, "Bengali Helpdesk")
    assert bot is not None
    convs = db.scalars(select(Conversation).where(Conversation.bot_id == bot.id)).all()
    assert len(convs) == 1
    msgs = db.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == convs[0].id)
    ).all()
    assert len(msgs) == 2


def test_missing_source_file(db):
    with pytest.raises(FileNotFoundError):
        migrate(
            source_path=Path("/tmp/does-not-exist-linguabot.db"),
            owner_email=ADMIN_EMAIL,
            db=db,
            dry_run=False,
        )


def test_missing_owner(linguabot_db, db):
    with pytest.raises(LookupError):
        migrate(
            source_path=linguabot_db,
            owner_email="ghost@nowhere.invalid",
            db=db,
            dry_run=False,
        )


def test_single_locale_maps_directly(tmp_path, db, clean):
    """If LinguaBot only supports one locale, that locale wins (not 'auto')."""
    owner_id = _owner_id(db)
    src = tmp_path / "single.db"
    _build_linguabot_db(src)
    # Re-run with supported_languages narrowed to one.
    conn = sqlite3.connect(src)
    conn.execute("UPDATE bots SET supported_languages = 'bn'")
    conn.commit()
    conn.close()

    migrate(source_path=src, owner_email=ADMIN_EMAIL, db=db, dry_run=False)
    bot = _imported_bot(db, owner_id, "Bengali Helpdesk")
    assert bot is not None
    assert bot.language_preset == "bn"
