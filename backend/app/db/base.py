"""Declarative SQLAlchemy base + universal columns + mixin helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ulid() -> str:
    """Generate a sortable 26-char ULID; fall back to uuid4 hex if the ulid lib is missing."""
    try:
        from ulid import ULID  # python-ulid

        return str(ULID())
    except Exception:
        try:
            import ulid  # ulid-py

            return str(ulid.new())
        except Exception:  # pragma: no cover
            return uuid.uuid4().hex


class Base(DeclarativeBase):
    """Common base. All ORM models inherit from this."""

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        # CamelCase -> snake_case, then pluralize naively (add 's')
        import re

        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        if not name.endswith("s"):
            name += "s"
        return name


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class IdMixin:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_ulid)
