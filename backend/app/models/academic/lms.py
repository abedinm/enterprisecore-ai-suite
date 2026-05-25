"""LMS Library — course materials uploaded by teachers/admins.

A resource may live on disk (``file_path``) or point at an external URL (a
YouTube link, a public Drive folder). Both are optional but at least one
should be set; we validate that in the schema rather than as a CHECK so the
table itself stays portable.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicLmsResource(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_lms_resources"

    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    department: Mapped[str] = mapped_column(
        String(120), default="", nullable=False, index=True
    )
    semester: Mapped[str] = mapped_column(
        String(120), default="", nullable=False
    )
    course_code: Mapped[str] = mapped_column(
        String(60), default="", nullable=False, index=True
    )
    # note | slide | past_exam | book_link | youtube | lab_report
    resource_type: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )
    file_path: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(500))
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Bumped every time POST /lms/resources/{id}/download is hit so the
    # "popular resources" view can sort by usage. Not a true file-server
    # counter — clients call the endpoint and we trust them — but it gives a
    # useful "this resource is doing the heavy lifting" signal for editors.
    download_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
