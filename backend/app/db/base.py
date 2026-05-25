"""Declarative SQLAlchemy base + universal columns + mixin helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, func
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


_VOWELS = set("aeiou")


def _pluralize(snake: str) -> str:
    """Best-effort English pluralization for class-derived table names.

    Handles the common patterns (-y/ies, -s/ses, -x/xes, -ch/ches, -sh/shes,
    already-plural, default +s). Models with surprising plurals (criteria,
    indices, etc.) should set `__tablename__` explicitly.
    """
    if snake.endswith("s"):
        return snake
    if len(snake) >= 2 and snake[-1] == "y" and snake[-2] not in _VOWELS:
        return snake[:-1] + "ies"
    if snake.endswith(("x", "ch", "sh", "ss")):
        return snake + "es"
    return snake + "s"


class Base(DeclarativeBase):
    """Common base. All ORM models inherit from this."""

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        import re

        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return _pluralize(snake)


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


class TenantMixin:
    """Mixin that adds a ``tenant_id`` FK column.

    Most business-data models compose this with ``IdMixin`` and ``TimestampMixin``.
    The ``tenant_id`` is auto-populated by the ``before_insert`` event listener
    in ``app/core/tenant_orm.py`` from the request's tenant context, so call
    sites don't have to pass it explicitly.
    """

    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
