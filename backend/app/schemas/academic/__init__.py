"""Re-exports for academic schemas — keeps endpoint imports tidy."""
from app.schemas.academic.advising import (  # noqa: F401
    AdvisingCreate, AdvisingNoteAppend, AdvisingOut, AdvisingUpdate,
    CgpaTrend, CgpaTrendPoint,
)
from app.schemas.academic.attendance import (  # noqa: F401
    AttendanceOut, AttendanceRecordIn, AttendanceStatus, AttendanceSummary,
    BulkAttendanceIn, ClassAttendanceReport,
)
from app.schemas.academic.classes import (  # noqa: F401
    ClassCreate, ClassOut, ClassUpdate, EnrollmentCreate, EnrollmentOut,
    EnrollmentUpdate,
)
from app.schemas.academic.core import (  # noqa: F401
    RoomCreate, RoomOut, RoomUpdate, SemesterCreate, SemesterOut,
    SemesterUpdate,
)
from app.schemas.academic.deadlines import (  # noqa: F401
    AssignmentCreate, AssignmentOut, AssignmentUpdate, StudentSubmissionUpsert,
    SubmissionCreate, SubmissionOut, SubmissionStatusPatch, SubmissionUpdate,
    UpcomingAssignmentOut,
)
from app.schemas.academic.exams import (  # noqa: F401
    ExamCalendarDay, ExamCreate, ExamOut, ExamScheduleRoomIn, ExamUpdate,
)
from app.schemas.academic.finance import (  # noqa: F401
    BudgetCreate, BudgetOut, BudgetStatusOut, BudgetStatusRow, BudgetUpdate,
    FinanceCategoryTotal, FinanceTrend, MonthlySummary, ScholarshipCreate,
    ScholarshipOut, ScholarshipUpdate, StudentFinanceCreate, StudentFinanceOut,
    StudentFinanceUpdate, TrendPoint,
)
from app.schemas.academic.group_projects import (  # noqa: F401
    AutoBalanceIn, AutoBalanceOut, AutoBalanceSuggestion, FairnessOut,
    GroupAssignmentCreate, GroupAssignmentOut, GroupAssignmentUpdate,
    GroupProjectCreate, GroupProjectOut, GroupProjectUpdate,
)
from app.schemas.academic.lab_reports import (  # noqa: F401
    LabReportClassSummaryRow, LabReportCreate, LabReportGrade, LabReportOut,
    LabReportStudentSummary, LabReportUpdate,
)
from app.schemas.academic.lms import (  # noqa: F401
    LmsDownloadOut, LmsResourceCreate, LmsResourceOut, LmsResourceUpdate,
)
from app.schemas.academic.study_aids import (  # noqa: F401
    QuizAttemptIn, QuizAttemptOut, QuizOut, QuizQuestion, StudyAidGenerateIn,
    StudyAidRegenerateIn, StudyNoteCreate, StudyNoteOut, StudyNoteUpdate,
)
from app.schemas.academic.study_match import (  # noqa: F401
    ConnectOut, CoursesUpdateIn, MatchPreview, StudyMatchOut,
    StudyProfileCreate, StudyProfileOut, StudyProfileUpdate,
)
from app.schemas.academic.timetable import (  # noqa: F401
    SlotCreate, SlotOut, SlotUpdate,
)
