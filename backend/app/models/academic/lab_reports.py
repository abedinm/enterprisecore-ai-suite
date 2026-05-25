"""Lab reports — student-authored, teacher-graded submissions."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicLabReport(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_lab_reports"

    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_id: Mapped[str] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    grade: Mapped[str | None] = mapped_column(String(16))
    feedback: Mapped[str | None] = mapped_column(Text)
    # draft | submitted | graded
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False, index=True
    )
