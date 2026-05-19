"""Initial baseline — generated tables match SQLAlchemy metadata.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-19

"""
from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.models import *  # noqa: F401,F403  — ensure every model is loaded

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
