"""Academic advising sessions — student-advisor meetings with CGPA tracking."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicAdvisingSession(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_advising_sessions"

    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    advisor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # CGPA: 0.00 .. 4.00 (or 5.00 for some scales), so 4 digits, 2 decimal.
    current_cgpa: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    target_cgpa: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    credits_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_remaining: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
