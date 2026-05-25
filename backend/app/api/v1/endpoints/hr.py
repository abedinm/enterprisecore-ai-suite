"""HR & people management endpoints — 12 tools."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import or_, select
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
    AttendanceIn, AttendanceOut, AttendanceSummaryOut, CandidateIn, CandidateOut,
    DisciplinaryIn, DisciplinaryOut, EmployeeIn, EmployeeOut, HRAnalyticsOut,
    JobOpeningIn, JobOpeningOut, LeaveBalanceOut, LeaveDecision, LeaveIn, LeaveOut,
    OnboardingTaskIn, OnboardingTaskOut, OrgUnitIn, OrgUnitNode, OrgUnitOut,
    PayslipOut, ReviewIn, ReviewOut, SelfServiceOut, TrainingIn, TrainingOut,
)
from app.services import hr as hr_svc
from app.services.audit import record_audit
from app.services.event_bus import publish_event

router = APIRouter()


def _audit(db: Session, user: User | None, action: str, entity_type: str,
           entity_id: str | None = None, detail: dict | None = None) -> None:
    record_audit(db, actor=user, action=action, entity_type=entity_type,
                 entity_id=entity_id, detail=detail or {})


# ============== Employees ================================================
@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(q: str | None = None, status: str | None = None,
                   department: str | None = None,
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Employee).order_by(Employee.full_name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Employee.full_name.ilike(like),
                              Employee.email.ilike(like),
                              Employee.employee_code.ilike(like)))
    if status:
        stmt = stmt.where(Employee.status == status)
    if department:
        stmt = stmt.where(Employee.department == department)
    return db.scalars(stmt.limit(1000)).all()


@router.get("/employees/{eid}", response_model=EmployeeOut)
def get_employee(eid: str, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    obj = db.get(Employee, eid)
    if not obj:
        raise NotFoundError("Employee not found")
    return obj


@router.post("/employees", response_model=EmployeeOut)
def create_employee(payload: EmployeeIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = Employee(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "employee", obj.id,
           {"name": obj.full_name, "code": obj.employee_code})
    db.commit()
    db.refresh(obj)
    publish_event(
        "hr.employee.created",
        payload={"employee_id": obj.id, "code": obj.employee_code, "name": obj.full_name},
        user_id=user.id,
    )
    return obj


@router.patch("/employees/{eid}", response_model=EmployeeOut)
def update_employee(eid: str, payload: EmployeeIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Employee, eid)
    if not obj:
        raise NotFoundError("Employee not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "employee", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/employees/{eid}", status_code=204)
def delete_employee(eid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Employee, eid)
    if obj:
        _audit(db, user, "delete", "employee", obj.id, {"name": obj.full_name})
        db.delete(obj)
        db.commit()
    return None


# ============== Attendance ===============================================
@router.get("/attendance", response_model=list[AttendanceOut])
def list_attendance(employee_id: str | None = None,
                    start: datetime | None = None, end: datetime | None = None,
                    db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(AttendanceRecord).order_by(AttendanceRecord.clock_in.desc())
    if employee_id:
        stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
    if start:
        stmt = stmt.where(AttendanceRecord.clock_in >= start)
    if end:
        stmt = stmt.where(AttendanceRecord.clock_in <= end)
    return db.scalars(stmt.limit(1000)).all()


@router.post("/attendance", response_model=AttendanceOut)
def record_attendance(payload: AttendanceIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    obj = AttendanceRecord(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "attendance", obj.id, {"employee_id": obj.employee_id})
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/attendance/{aid}/clock-out", response_model=AttendanceOut)
def clock_out(aid: str, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    rec = db.get(AttendanceRecord, aid)
    if not rec:
        raise NotFoundError("Attendance record not found")
    rec.clock_out = datetime.now(timezone.utc)
    _audit(db, user, "clock_out", "attendance", rec.id)
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/attendance/{aid}", status_code=204)
def delete_attendance(aid: str, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    rec = db.get(AttendanceRecord, aid)
    if rec:
        _audit(db, user, "delete", "attendance", rec.id)
        db.delete(rec)
        db.commit()
    return None


@router.get("/attendance/summary/{employee_id}", response_model=AttendanceSummaryOut)
def attendance_summary_endpoint(employee_id: str, db: Session = Depends(get_db),
                               _: User = Depends(get_current_user)):
    return AttendanceSummaryOut(**hr_svc.attendance_summary(db, employee_id))


# ============== Leaves ===================================================
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
                  user: User = Depends(get_current_user)):
    obj = LeaveRequest(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "leave", obj.id,
           {"employee_id": obj.employee_id, "type": obj.leave_type})
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/leaves/{lid}/decision", response_model=LeaveOut)
def decide_leave(lid: str, payload: LeaveDecision, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(LeaveRequest, lid)
    if not obj:
        raise NotFoundError("Leave request not found")
    if payload.status not in {"approved", "rejected", "cancelled", "pending"}:
        raise NotFoundError("Invalid status")
    obj.status = payload.status
    _audit(db, user, "decision", "leave", obj.id, {"status": payload.status})
    db.commit()
    db.refresh(obj)
    if payload.status == "approved":
        publish_event(
            "hr.leave.approved",
            payload={"leave_id": obj.id, "employee_id": obj.employee_id},
            user_id=user.id,
        )
    return obj


@router.delete("/leaves/{lid}", status_code=204)
def delete_leave(lid: str, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(LeaveRequest, lid)
    if obj:
        _audit(db, user, "delete", "leave", obj.id)
        db.delete(obj)
        db.commit()
    return None


@router.get("/leaves/balance/{employee_id}", response_model=LeaveBalanceOut)
def leave_balance(employee_id: str, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return LeaveBalanceOut(**hr_svc.leave_balance(db, employee_id))


# ============== Reviews ===================================================
@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(employee_id: str | None = None, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    stmt = select(PerformanceReview).order_by(PerformanceReview.created_at.desc())
    if employee_id:
        stmt = stmt.where(PerformanceReview.employee_id == employee_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/reviews", response_model=ReviewOut)
def create_review(payload: ReviewIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = PerformanceReview(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "review", obj.id,
           {"employee_id": obj.employee_id, "period": obj.period})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/reviews/{rid}", response_model=ReviewOut)
def update_review(rid: str, payload: ReviewIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(PerformanceReview, rid)
    if not obj:
        raise NotFoundError("Review not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "review", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/reviews/{rid}", status_code=204)
def delete_review(rid: str, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(PerformanceReview, rid)
    if obj:
        _audit(db, user, "delete", "review", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Recruitment ===============================================
@router.get("/openings", response_model=list[JobOpeningOut])
def list_openings(status: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(JobOpening).order_by(JobOpening.created_at.desc())
    if status:
        stmt = stmt.where(JobOpening.status == status)
    return db.scalars(stmt).all()


@router.post("/openings", response_model=JobOpeningOut)
def create_opening(payload: JobOpeningIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = JobOpening(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "job_opening", obj.id, {"title": obj.title})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/openings/{oid}", response_model=JobOpeningOut)
def update_opening(oid: str, payload: JobOpeningIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(JobOpening, oid)
    if not obj:
        raise NotFoundError("Job opening not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "job_opening", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/openings/{oid}", status_code=204)
def delete_opening(oid: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(JobOpening, oid)
    if obj:
        _audit(db, user, "delete", "job_opening", obj.id, {"title": obj.title})
        db.delete(obj)
        db.commit()
    return None


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
                  user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = Candidate(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "candidate", obj.id, {"name": obj.full_name})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/candidates/{cid}", response_model=CandidateOut)
def update_candidate(cid: str, payload: CandidateIn, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Candidate, cid)
    if not obj:
        raise NotFoundError("Candidate not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "candidate", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/candidates/{cid}", status_code=204)
def delete_candidate(cid: str, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Candidate, cid)
    if obj:
        _audit(db, user, "delete", "candidate", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Onboarding ================================================
@router.get("/onboarding", response_model=list[OnboardingTaskOut])
def list_onboarding(employee_id: str | None = None, status: str | None = None,
                    db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(OnboardingTask).order_by(OnboardingTask.due_date)
    if employee_id:
        stmt = stmt.where(OnboardingTask.employee_id == employee_id)
    if status:
        stmt = stmt.where(OnboardingTask.status == status)
    return db.scalars(stmt).all()


@router.post("/onboarding", response_model=OnboardingTaskOut)
def add_onboarding(payload: OnboardingTaskIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = OnboardingTask(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "onboarding_task", obj.id, {"title": obj.title})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/onboarding/{tid}", response_model=OnboardingTaskOut)
def update_onboarding(tid: str, payload: OnboardingTaskIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    obj = db.get(OnboardingTask, tid)
    if not obj:
        raise NotFoundError("Onboarding task not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "onboarding_task", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/onboarding/{tid}", status_code=204)
def delete_onboarding(tid: str, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(OnboardingTask, tid)
    if obj:
        _audit(db, user, "delete", "onboarding_task", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Org Chart =================================================
@router.get("/org-units", response_model=list[OrgUnitOut])
def list_org_units(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(OrgUnit).order_by(OrgUnit.name)).all()


@router.post("/org-units", response_model=OrgUnitOut)
def create_org_unit(payload: OrgUnitIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = OrgUnit(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "org_unit", obj.id, {"name": obj.name})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/org-units/{uid}", response_model=OrgUnitOut)
def update_org_unit(uid: str, payload: OrgUnitIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(OrgUnit, uid)
    if not obj:
        raise NotFoundError("Org unit not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "org_unit", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/org-units/{uid}", status_code=204)
def delete_org_unit(uid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(OrgUnit, uid)
    if obj:
        _audit(db, user, "delete", "org_unit", obj.id, {"name": obj.name})
        db.delete(obj)
        db.commit()
    return None


@router.get("/org-chart", response_model=list[OrgUnitNode])
def org_chart(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return hr_svc.build_org_tree(db)


# ============== Payslips =================================================
@router.get("/payslips/{employee_id}", response_model=list[PayslipOut])
def employee_payslips(employee_id: str, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    return [PayslipOut(**p) for p in hr_svc.employee_payslips(db, employee_id)]


@router.get("/payslips/{employee_id}/{payroll_run_id}/pdf")
def payslip_pdf(employee_id: str, payroll_run_id: str,
                db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    payslips = hr_svc.employee_payslips(db, employee_id)
    payslip = next((p for p in payslips if p["payroll_run_id"] == payroll_run_id), None)
    if not payslip:
        raise NotFoundError("Payslip not found")
    pdf = hr_svc.render_payslip_pdf(payslip)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="payslip-{employee_id}-{payslip["period_end"]}.pdf"'},
    )


# ============== Training =================================================
@router.get("/training", response_model=list[TrainingOut])
def list_training(employee_id: str | None = None, status: str | None = None,
                  db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(TrainingRecord).order_by(TrainingRecord.created_at.desc())
    if employee_id:
        stmt = stmt.where(TrainingRecord.employee_id == employee_id)
    if status:
        stmt = stmt.where(TrainingRecord.status == status)
    return db.scalars(stmt).all()


@router.post("/training", response_model=TrainingOut)
def add_training(payload: TrainingIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = TrainingRecord(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "training", obj.id,
           {"employee_id": obj.employee_id, "course": obj.course_name})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/training/{tid}", response_model=TrainingOut)
def update_training(tid: str, payload: TrainingIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    obj = db.get(TrainingRecord, tid)
    if not obj:
        raise NotFoundError("Training record not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    if payload.status == "completed" and not obj.completed_at:
        obj.completed_at = datetime.now(timezone.utc)
    _audit(db, user, "update", "training", obj.id, {"status": obj.status})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/training/{tid}", status_code=204)
def delete_training(tid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(TrainingRecord, tid)
    if obj:
        _audit(db, user, "delete", "training", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Self Service =============================================
@router.get("/me", response_model=SelfServiceOut)
def self_service(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = hr_svc.current_user_employee(db, user.id)
    if not emp:
        return SelfServiceOut(employee=None)
    recent_att = db.scalars(
        select(AttendanceRecord)
        .where(AttendanceRecord.employee_id == emp.id)
        .order_by(AttendanceRecord.clock_in.desc())
        .limit(10)
    ).all()
    upcoming_leaves = db.scalars(
        select(LeaveRequest)
        .where(LeaveRequest.employee_id == emp.id,
               LeaveRequest.end_date >= date.today())
        .order_by(LeaveRequest.start_date)
    ).all()
    open_tasks = db.scalars(
        select(OnboardingTask)
        .where(OnboardingTask.employee_id == emp.id,
               OnboardingTask.status != "completed")
        .order_by(OnboardingTask.due_date)
    ).all()
    training = db.scalars(
        select(TrainingRecord)
        .where(TrainingRecord.employee_id == emp.id)
        .order_by(TrainingRecord.created_at.desc())
    ).all()
    payslips = [PayslipOut(**p) for p in hr_svc.employee_payslips(db, emp.id)]
    return SelfServiceOut(
        employee=EmployeeOut.model_validate(emp),
        recent_attendance=[AttendanceOut.model_validate(a) for a in recent_att],
        upcoming_leaves=[LeaveOut.model_validate(l) for l in upcoming_leaves],
        open_onboarding=[OnboardingTaskOut.model_validate(t) for t in open_tasks],
        training=[TrainingOut.model_validate(t) for t in training],
        payslips=payslips,
    )


@router.post("/me/clock-in", response_model=AttendanceOut)
def me_clock_in(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = hr_svc.current_user_employee(db, user.id)
    if not emp:
        raise NotFoundError("No employee record linked to this user")
    rec = AttendanceRecord(employee_id=emp.id, clock_in=datetime.now(timezone.utc),
                           source="self_service")
    db.add(rec)
    db.flush()
    _audit(db, user, "clock_in", "attendance", rec.id, {"employee_id": emp.id})
    db.commit()
    db.refresh(rec)
    return rec


@router.post("/me/clock-out", response_model=AttendanceOut)
def me_clock_out(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = hr_svc.current_user_employee(db, user.id)
    if not emp:
        raise NotFoundError("No employee record linked to this user")
    rec = db.scalar(
        select(AttendanceRecord)
        .where(AttendanceRecord.employee_id == emp.id,
               AttendanceRecord.clock_out.is_(None))
        .order_by(AttendanceRecord.clock_in.desc())
        .limit(1)
    )
    if not rec:
        raise NotFoundError("No open attendance record to close")
    rec.clock_out = datetime.now(timezone.utc)
    _audit(db, user, "clock_out", "attendance", rec.id, {"employee_id": emp.id})
    db.commit()
    db.refresh(rec)
    return rec


@router.post("/me/leave-request", response_model=LeaveOut)
def me_request_leave(payload: LeaveIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    emp = hr_svc.current_user_employee(db, user.id)
    if not emp:
        raise NotFoundError("No employee record linked to this user")
    payload_dict = payload.model_dump()
    payload_dict["employee_id"] = emp.id
    obj = LeaveRequest(**payload_dict)
    db.add(obj)
    db.flush()
    _audit(db, user, "self_request", "leave", obj.id,
           {"type": obj.leave_type, "days": (obj.end_date - obj.start_date).days + 1})
    db.commit()
    db.refresh(obj)
    return obj


# ============== Discipline ===============================================
@router.get("/disciplinary", response_model=list[DisciplinaryOut])
def list_disciplinary(employee_id: str | None = None, db: Session = Depends(get_db),
                      _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    stmt = select(DisciplinaryRecord).order_by(DisciplinaryRecord.incident_date.desc())
    if employee_id:
        stmt = stmt.where(DisciplinaryRecord.employee_id == employee_id)
    return db.scalars(stmt).all()


@router.post("/disciplinary", response_model=DisciplinaryOut)
def add_disciplinary(payload: DisciplinaryIn, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(UserRole.admin))):
    obj = DisciplinaryRecord(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "disciplinary", obj.id,
           {"employee_id": obj.employee_id, "severity": obj.severity})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/disciplinary/{did}", response_model=DisciplinaryOut)
def update_disciplinary(did: str, payload: DisciplinaryIn, db: Session = Depends(get_db),
                        user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(DisciplinaryRecord, did)
    if not obj:
        raise NotFoundError("Disciplinary record not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "disciplinary", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/disciplinary/{did}", status_code=204)
def delete_disciplinary(did: str, db: Session = Depends(get_db),
                        user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(DisciplinaryRecord, did)
    if obj:
        _audit(db, user, "delete", "disciplinary", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Analytics ================================================
@router.get("/analytics", response_model=HRAnalyticsOut)
def hr_analytics_endpoint(db: Session = Depends(get_db),
                          _: User = Depends(get_current_user)):
    return HRAnalyticsOut(**hr_svc.hr_analytics(db))
