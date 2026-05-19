"""HR & people management endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.hr import (
    AttendanceRecord, Candidate, DisciplinaryRecord, Employee, JobOpening,
    LeaveRequest, OnboardingTask, OrgUnit, PerformanceReview, TrainingRecord,
)
from app.models.user import User, UserRole
from app.schemas.hr import (
    AttendanceIn, AttendanceOut, CandidateIn, CandidateOut, DisciplinaryIn,
    DisciplinaryOut, EmployeeIn, EmployeeOut, HRAnalyticsOut, JobOpeningIn,
    JobOpeningOut, LeaveDecision, LeaveIn, LeaveOut, OnboardingTaskIn,
    OnboardingTaskOut, OrgUnitIn, OrgUnitOut, ReviewIn, ReviewOut, TrainingIn,
    TrainingOut,
)

router = APIRouter()


def _crud_simple(model, IN, OUT, db, payload, item_id=None):
    """Tiny helper for create/update."""
    if item_id:
        obj = db.get(model, item_id)
        if not obj:
            raise NotFoundError(f"{model.__name__} not found")
        for k, v in payload.model_dump().items():
            setattr(obj, k, v)
    else:
        obj = model(**payload.model_dump())
        db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Employees ----------------------------------------------------------
@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(q: str | None = None, status: str | None = None,
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Employee).order_by(Employee.full_name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Employee.full_name.ilike(like),
                              Employee.email.ilike(like),
                              Employee.employee_code.ilike(like)))
    if status:
        stmt = stmt.where(Employee.status == status)
    return db.scalars(stmt.limit(1000)).all()


@router.post("/employees", response_model=EmployeeOut)
def create_employee(payload: EmployeeIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(Employee, EmployeeIn, EmployeeOut, db, payload)


@router.patch("/employees/{eid}", response_model=EmployeeOut)
def update_employee(eid: str, payload: EmployeeIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(Employee, EmployeeIn, EmployeeOut, db, payload, item_id=eid)


@router.delete("/employees/{eid}", status_code=204)
def delete_employee(eid: str, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Employee, eid)
    if obj:
        db.delete(obj)
        db.commit()
    return None


# ---- Attendance ---------------------------------------------------------
@router.get("/attendance", response_model=list[AttendanceOut])
def list_attendance(employee_id: str | None = None, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(AttendanceRecord).order_by(AttendanceRecord.clock_in.desc())
    if employee_id:
        stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/attendance", response_model=AttendanceOut)
def record_attendance(payload: AttendanceIn, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    return _crud_simple(AttendanceRecord, AttendanceIn, AttendanceOut, db, payload)


@router.post("/attendance/{eid}/clock-out", response_model=AttendanceOut)
def clock_out(eid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rec = db.get(AttendanceRecord, eid)
    if not rec:
        raise NotFoundError("Attendance record not found")
    rec.clock_out = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return rec


# ---- Leaves -------------------------------------------------------------
@router.get("/leaves", response_model=list[LeaveOut])
def list_leaves(status: str | None = None, employee_id: str | None = None,
                db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(LeaveRequest).order_by(LeaveRequest.start_date.desc())
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    if employee_id:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/leaves", response_model=LeaveOut)
def request_leave(payload: LeaveIn, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return _crud_simple(LeaveRequest, LeaveIn, LeaveOut, db, payload)


@router.post("/leaves/{lid}/decision", response_model=LeaveOut)
def decide_leave(lid: str, payload: LeaveDecision, db: Session = Depends(get_db),
                 _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(LeaveRequest, lid)
    if not obj:
        raise NotFoundError("Leave request not found")
    if payload.status not in {"approved", "rejected", "cancelled"}:
        raise NotFoundError("Invalid status")
    obj.status = payload.status
    db.commit()
    db.refresh(obj)
    return obj


# ---- Reviews ------------------------------------------------------------
@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(employee_id: str | None = None, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    stmt = select(PerformanceReview).order_by(PerformanceReview.created_at.desc())
    if employee_id:
        stmt = stmt.where(PerformanceReview.employee_id == employee_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/reviews", response_model=ReviewOut)
def create_review(payload: ReviewIn, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(PerformanceReview, ReviewIn, ReviewOut, db, payload)


# ---- Recruitment --------------------------------------------------------
@router.get("/openings", response_model=list[JobOpeningOut])
def list_openings(status: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(JobOpening).order_by(JobOpening.created_at.desc())
    if status:
        stmt = stmt.where(JobOpening.status == status)
    return db.scalars(stmt).all()


@router.post("/openings", response_model=JobOpeningOut)
def create_opening(payload: JobOpeningIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(JobOpening, JobOpeningIn, JobOpeningOut, db, payload)


@router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(job_opening_id: str | None = None, stage: str | None = None,
                    db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Candidate).order_by(Candidate.created_at.desc())
    if job_opening_id:
        stmt = stmt.where(Candidate.job_opening_id == job_opening_id)
    if stage:
        stmt = stmt.where(Candidate.stage == stage)
    return db.scalars(stmt).all()


@router.post("/candidates", response_model=CandidateOut)
def add_candidate(payload: CandidateIn, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(Candidate, CandidateIn, CandidateOut, db, payload)


@router.patch("/candidates/{cid}", response_model=CandidateOut)
def update_candidate(cid: str, payload: CandidateIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(Candidate, CandidateIn, CandidateOut, db, payload, item_id=cid)


# ---- Onboarding, Org chart, Training, Discipline -----------------------
@router.get("/onboarding", response_model=list[OnboardingTaskOut])
def list_onboarding(employee_id: str | None = None, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(OnboardingTask)
    if employee_id:
        stmt = stmt.where(OnboardingTask.employee_id == employee_id)
    return db.scalars(stmt).all()


@router.post("/onboarding", response_model=OnboardingTaskOut)
def add_onboarding(payload: OnboardingTaskIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(OnboardingTask, OnboardingTaskIn, OnboardingTaskOut, db, payload)


@router.patch("/onboarding/{tid}", response_model=OnboardingTaskOut)
def update_onboarding(tid: str, payload: OnboardingTaskIn, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    return _crud_simple(OnboardingTask, OnboardingTaskIn, OnboardingTaskOut, db, payload, item_id=tid)


@router.get("/org-units", response_model=list[OrgUnitOut])
def list_org_units(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(OrgUnit).order_by(OrgUnit.name)).all()


@router.post("/org-units", response_model=OrgUnitOut)
def create_org_unit(payload: OrgUnitIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(OrgUnit, OrgUnitIn, OrgUnitOut, db, payload)


@router.get("/training", response_model=list[TrainingOut])
def list_training(employee_id: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(TrainingRecord).order_by(TrainingRecord.created_at.desc())
    if employee_id:
        stmt = stmt.where(TrainingRecord.employee_id == employee_id)
    return db.scalars(stmt).all()


@router.post("/training", response_model=TrainingOut)
def add_training(payload: TrainingIn, db: Session = Depends(get_db),
                 _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud_simple(TrainingRecord, TrainingIn, TrainingOut, db, payload)


@router.get("/disciplinary", response_model=list[DisciplinaryOut])
def list_disciplinary(employee_id: str | None = None, db: Session = Depends(get_db),
                      _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    stmt = select(DisciplinaryRecord).order_by(DisciplinaryRecord.incident_date.desc())
    if employee_id:
        stmt = stmt.where(DisciplinaryRecord.employee_id == employee_id)
    return db.scalars(stmt).all()


@router.post("/disciplinary", response_model=DisciplinaryOut)
def add_disciplinary(payload: DisciplinaryIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin))):
    return _crud_simple(DisciplinaryRecord, DisciplinaryIn, DisciplinaryOut, db, payload)


# ---- Analytics ----------------------------------------------------------
@router.get("/analytics", response_model=HRAnalyticsOut)
def hr_analytics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    headcount = db.scalar(select(func.count(Employee.id))) or 0
    active = db.scalar(select(func.count(Employee.id)).where(Employee.status == "active")) or 0
    on_leave = db.scalar(select(func.count(Employee.id)).where(Employee.status == "on_leave")) or 0
    avg_salary = db.scalar(select(func.coalesce(func.avg(Employee.salary), 0))) or Decimal("0")
    open_pos = db.scalar(select(func.count(JobOpening.id)).where(JobOpening.status == "open")) or 0
    cand_pipe = db.scalar(select(func.count(Candidate.id)).where(Candidate.stage.in_(("applied", "screening", "interview", "offer")))) or 0
    leaves_pending = db.scalar(select(func.count(LeaveRequest.id)).where(LeaveRequest.status == "pending")) or 0
    dept_rows = db.execute(
        select(Employee.department, func.count(Employee.id))
        .where(Employee.department.isnot(None))
        .group_by(Employee.department)
    ).all()
    return HRAnalyticsOut(
        headcount=headcount, active=active, on_leave=on_leave,
        by_department={(d or "Unassigned"): c for d, c in dept_rows},
        avg_salary=Decimal(avg_salary),
        open_positions=open_pos, candidates_in_pipeline=cand_pipe,
        pending_leave_requests=leaves_pending,
    )
