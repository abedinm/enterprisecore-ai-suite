"""Study group matching — opt-in profiles + computed pair scores."""
from __future__ import annotations

from sqlalchemy import (Boolean, ForeignKey, Integer, JSON, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicStudyProfile(IdMixin, TenantMixin, TimestampMixin, Base):
    """A student's opt-in profile for study-group discovery. One per student."""

    __tablename__ = "academic_study_profiles"

    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    university: Mapped[str] = mapped_column(
        String(180), default="", nullable=False
    )
    department: Mapped[str] = mapped_column(
        String(120), default="", nullable=False
    )
    semester: Mapped[str] = mapped_column(
        String(60), default="", nullable=False
    )
    # JSON list[str] of course codes the student is taking
    courses: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    goals: Mapped[str] = mapped_column(Text, default="", nullable=False)
    preferred_time: Mapped[str] = mapped_column(
        String(60), default="", nullable=False
    )
    study_style: Mapped[str] = mapped_column(
        String(60), default="", nullable=False
    )
    online_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AcademicStudyGroupMatch(IdMixin, TenantMixin, TimestampMixin, Base):
    """A computed compatibility score between two students.

    Pair is stored unordered (student_a_id < student_b_id) so the unique
    constraint catches both ``(A,B)`` and ``(B,A)`` as the same pair. The
    service is responsible for sorting before insert.
    """

    __tablename__ = "academic_study_group_matches"

    student_a_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_b_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 0..100 compatibility score
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "student_a_id", "student_b_id",
            name="uq_academic_study_match_pair",
        ),
    )
