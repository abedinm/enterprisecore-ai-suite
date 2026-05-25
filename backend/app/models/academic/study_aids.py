"""Study aids — AI-generated summaries, flashcards, MCQs from source text."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicStudyNote(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_study_notes"

    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # JSON list[{front, back}] flashcards.
    flashcards: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # JSON list[{question, options[], answer_index}] MCQs.
    mcqs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # paste | upload
    source_type: Mapped[str] = mapped_column(
        String(16), default="paste", nullable=False
    )


class AcademicStudyQuizAttempt(IdMixin, TenantMixin, TimestampMixin, Base):
    """One record per quiz attempt — score over total on a study note's MCQs.

    Kept deliberately small: we record the headline number for the dashboard
    and the timestamp, not the per-question answers. That trade-off keeps the
    table cheap to query for "recent activity" widgets while leaving the door
    open for a richer attempt-detail table later if reviewers want it.
    """

    __tablename__ = "academic_study_quiz_attempts"

    note_id: Mapped[str] = mapped_column(
        ForeignKey("academic_study_notes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
