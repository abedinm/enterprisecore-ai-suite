"""Academic module pack — SQLAlchemy models.

Imported once from app/models/__init__.py so SQLAlchemy's declarative base
sees every academic_* table. Submodules are split by domain so each file is
small enough to read end-to-end while writing service logic.
"""
from app.models.academic.advising import AcademicAdvisingSession  # noqa: F401
from app.models.academic.attendance import AcademicAttendanceRecord  # noqa: F401
from app.models.academic.classes import (  # noqa: F401
    AcademicClass, AcademicClassEnrollment,
)
from app.models.academic.core import AcademicRoom, AcademicSemester  # noqa: F401
from app.models.academic.deadlines import (  # noqa: F401
    AcademicAssignment, AcademicAssignmentSubmission,
)
from app.models.academic.exams import AcademicExam  # noqa: F401
from app.models.academic.finance import (  # noqa: F401
    AcademicScholarship, AcademicStudentBudget, AcademicStudentFinanceRecord,
)
from app.models.academic.group_projects import (  # noqa: F401
    AcademicGroupProject, AcademicGroupProjectAssignment,
)
from app.models.academic.lab_reports import AcademicLabReport  # noqa: F401
from app.models.academic.lms import AcademicLmsResource  # noqa: F401
from app.models.academic.study_aids import (  # noqa: F401
    AcademicStudyNote, AcademicStudyQuizAttempt,
)
from app.models.academic.study_match import (  # noqa: F401
    AcademicStudyGroupMatch, AcademicStudyProfile,
)
from app.models.academic.timetable import AcademicTimetableSlot  # noqa: F401

__all__ = [
    "AcademicAdvisingSession",
    "AcademicAssignment",
    "AcademicAssignmentSubmission",
    "AcademicAttendanceRecord",
    "AcademicClass",
    "AcademicClassEnrollment",
    "AcademicExam",
    "AcademicGroupProject",
    "AcademicGroupProjectAssignment",
    "AcademicLabReport",
    "AcademicLmsResource",
    "AcademicRoom",
    "AcademicScholarship",
    "AcademicSemester",
    "AcademicStudentBudget",
    "AcademicStudentFinanceRecord",
    "AcademicStudyGroupMatch",
    "AcademicStudyNote",
    "AcademicStudyProfile",
    "AcademicStudyQuizAttempt",
    "AcademicTimetableSlot",
]
