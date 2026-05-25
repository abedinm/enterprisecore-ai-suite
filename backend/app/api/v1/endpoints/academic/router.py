"""Parent router for the academic module pack.

Every sub-router under this file inherits the ``require_plan_feature("academic")``
dependency from the parent, so removing the academic feature from the active
plan disappears every academic endpoint with one switch flip.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_plan_feature
from app.api.v1.endpoints.academic import (
    advising, attendance, classes, core, deadlines, exams, finance,
    group_projects, lab_reports, lms, study_aids, study_match, timetable,
)

router = APIRouter(
    dependencies=[Depends(require_plan_feature("academic"))],
)

# Core primitives (semesters + rooms) live at the package root.
router.include_router(core.router, tags=["academic-core"])
router.include_router(classes.router, prefix="/classes", tags=["academic-classes"])
router.include_router(attendance.router, tags=["academic-attendance"])
router.include_router(timetable.router, prefix="/timetable", tags=["academic-timetable"])
router.include_router(lms.router, prefix="/lms", tags=["academic-lms"])
router.include_router(lab_reports.router, prefix="/lab", tags=["academic-lab-reports"])
router.include_router(exams.router, prefix="/exams", tags=["academic-exams"])
router.include_router(advising.router, prefix="/advising", tags=["academic-advising"])
router.include_router(
    group_projects.router, prefix="/group", tags=["academic-group-projects"],
)
router.include_router(study_aids.router, prefix="/study-aids", tags=["academic-study-aids"])
router.include_router(
    study_match.router, prefix="/study-match", tags=["academic-study-match"],
)
router.include_router(finance.router, prefix="/finance", tags=["academic-finance"])
router.include_router(deadlines.router, prefix="/deadlines", tags=["academic-deadlines"])
