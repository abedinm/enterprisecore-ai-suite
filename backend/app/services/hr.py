"""HR business logic: org-chart tree, payslip aggregation, payslip PDF, analytics."""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import PayrollRun, PayslipLine
from app.models.hr import (
    AttendanceRecord, Candidate, DisciplinaryRecord, Employee, JobOpening,
    LeaveRequest, OnboardingTask, OrgUnit, PerformanceReview, TrainingRecord,
)


def build_org_tree(db: Session) -> list[dict]:
    """Return forest of org units as nested dicts with headcount + manager_name."""
    units = db.scalars(select(OrgUnit).order_by(OrgUnit.name)).all()
    employees = db.scalars(select(Employee)).all()
    headcount_by_unit: dict[str, int] = defaultdict(int)
    for emp in employees:
        if emp.department:
            headcount_by_unit[emp.department] += 1
    manager_name_by_id = {e.id: e.full_name for e in employees}

    by_id: dict[str, dict] = {}
    for u in units:
        by_id[u.id] = {
            "id": u.id,
            "name": u.name,
            "manager_employee_id": u.manager_employee_id,
            "manager_name": manager_name_by_id.get(u.manager_employee_id) if u.manager_employee_id else None,
            "headcount": headcount_by_unit.get(u.name, 0),
            "children": [],
        }
    roots = []
    for u in units:
        node = by_id[u.id]
        if u.parent_id and u.parent_id in by_id:
            by_id[u.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def employee_payslips(db: Session, employee_id: str) -> list[dict]:
    """Collect payslips for an employee from PayslipLine records across PayrollRuns."""
    lines = db.scalars(
        select(PayslipLine).where(PayslipLine.employee_id == employee_id)
    ).all()
    by_run: dict[str, list[PayslipLine]] = defaultdict(list)
    for line in lines:
        by_run[line.payroll_run_id].append(line)

    employee = db.get(Employee, employee_id) if employee_id else None
    emp_name = employee.full_name if employee else None

    result = []
    for run_id, run_lines in by_run.items():
        run = db.get(PayrollRun, run_id)
        if not run:
            continue
        gross = sum((Decimal(str(l.amount)) for l in run_lines if l.kind in ("earning", "bonus")), Decimal("0"))
        deductions = sum((Decimal(str(l.amount)) for l in run_lines if l.kind in ("tax", "deduction")), Decimal("0"))
        result.append({
            "payroll_run_id": run.id,
            "employee_id": employee_id,
            "employee_name": emp_name,
            "period_start": run.period_start,
            "period_end": run.period_end,
            "gross": gross,
            "deductions": deductions,
            "net": gross - deductions,
            "currency": "USD",
            "lines": [{"label": l.label, "amount": l.amount, "kind": l.kind} for l in run_lines],
        })
    result.sort(key=lambda r: r["period_end"], reverse=True)
    return result


def render_payslip_pdf(payslip: dict, company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Payslip {payslip['period_start']}-{payslip['period_end']}")
    styles = getSampleStyleSheet()
    story: list = []
    story.append(Paragraph(f"<b>{company_name}</b>", styles["Title"]))
    story.append(Paragraph(
        f"Payslip · {payslip['period_start']} → {payslip['period_end']}",
        styles["BodyText"],
    ))
    story.append(Spacer(1, 4 * mm))

    meta = [
        ["Employee:", payslip.get("employee_name") or "—"],
        ["Employee ID:", payslip.get("employee_id") or "—"],
        ["Currency:", payslip.get("currency", "USD")],
    ]
    mt = Table(meta, colWidths=[35 * mm, 120 * mm])
    mt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(mt)
    story.append(Spacer(1, 6 * mm))

    rows = [["Label", "Kind", "Amount"]]
    for line in payslip["lines"]:
        rows.append([line["label"], line["kind"], f"{payslip.get('currency','USD')} {line['amount']:.2f}"])
    t = Table(rows, colWidths=[90 * mm, 30 * mm, 50 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    totals = [
        ["Gross", f"{payslip.get('currency','USD')} {payslip['gross']:.2f}"],
        ["Deductions", f"-{payslip.get('currency','USD')} {payslip['deductions']:.2f}"],
        ["Net pay", f"{payslip.get('currency','USD')} {payslip['net']:.2f}"],
    ]
    tot = Table(totals, colWidths=[60 * mm, 40 * mm], hAlign="RIGHT")
    tot.setStyle(TableStyle([
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(tot)

    doc.build(story)
    return buffer.getvalue()


def attendance_summary(db: Session, employee_id: str) -> dict:
    records = db.scalars(
        select(AttendanceRecord).where(AttendanceRecord.employee_id == employee_id)
    ).all()
    distinct_days = set()
    hours = Decimal("0")
    last_in = None
    for r in records:
        if r.clock_in:
            distinct_days.add(r.clock_in.date())
            if not last_in or r.clock_in > last_in:
                last_in = r.clock_in
            if r.clock_out:
                delta = (r.clock_out - r.clock_in).total_seconds() / 3600
                hours += Decimal(str(round(delta, 2)))
    return {
        "employee_id": employee_id,
        "days_present": len(distinct_days),
        "hours_total": hours,
        "last_clock_in": last_in,
    }


def leave_balance(db: Session, employee_id: str) -> dict:
    """Approved-leave-days summed by leave_type for the year-to-date."""
    today = date.today()
    start = today.replace(month=1, day=1)
    rows = db.execute(
        select(LeaveRequest.leave_type, LeaveRequest.start_date, LeaveRequest.end_date)
        .where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date >= start,
        )
    ).all()
    by_type: dict[str, int] = defaultdict(int)
    total = 0
    for lt, s, e in rows:
        days = (e - s).days + 1
        by_type[lt or "general"] += days
        total += days
    return {
        "employee_id": employee_id,
        "by_type": dict(by_type),
        "total_taken": total,
    }


def hr_analytics(db: Session) -> dict:
    headcount = db.scalar(select(func.count(Employee.id))) or 0
    active = db.scalar(select(func.count(Employee.id)).where(Employee.status == "active")) or 0
    on_leave = db.scalar(select(func.count(Employee.id)).where(Employee.status == "on_leave")) or 0
    avg_salary = db.scalar(select(func.coalesce(func.avg(Employee.salary), 0))) or Decimal("0")
    open_pos = db.scalar(select(func.count(JobOpening.id)).where(JobOpening.status == "open")) or 0
    cand_pipe = db.scalar(
        select(func.count(Candidate.id))
        .where(Candidate.stage.in_(("applied", "screening", "interview", "offer")))
    ) or 0
    leaves_pending = db.scalar(
        select(func.count(LeaveRequest.id)).where(LeaveRequest.status == "pending")
    ) or 0

    dept_rows = db.execute(
        select(Employee.department, func.count(Employee.id))
        .group_by(Employee.department)
    ).all()
    by_department = {(d or "Unassigned"): c for d, c in dept_rows}

    status_rows = db.execute(
        select(Employee.status, func.count(Employee.id)).group_by(Employee.status)
    ).all()
    by_status = {s or "unknown": c for s, c in status_rows}

    hires_rows = db.execute(
        select(Employee.hire_date, func.count(Employee.id))
        .where(Employee.hire_date.isnot(None))
        .group_by(Employee.hire_date)
    ).all()
    hires_by_month: dict[str, int] = defaultdict(int)
    for d, c in hires_rows:
        if d:
            hires_by_month[d.strftime("%Y-%m")] += c

    review_avg = db.scalar(
        select(func.coalesce(func.avg(PerformanceReview.score), 0))
    ) or Decimal("0")
    training_total = db.scalar(select(func.count(TrainingRecord.id))) or 0
    training_done = db.scalar(
        select(func.count(TrainingRecord.id)).where(TrainingRecord.status == "completed")
    ) or 0
    completion_rate = (Decimal(training_done) / Decimal(training_total)).quantize(Decimal("0.0001")) \
        if training_total else Decimal("0")
    disciplinary_count = db.scalar(select(func.count(DisciplinaryRecord.id))) or 0

    return {
        "headcount": headcount,
        "active": active,
        "on_leave": on_leave,
        "by_department": by_department,
        "avg_salary": Decimal(avg_salary),
        "open_positions": open_pos,
        "candidates_in_pipeline": cand_pipe,
        "pending_leave_requests": leaves_pending,
        "by_status": by_status,
        "hires_by_month": dict(sorted(hires_by_month.items())),
        "review_avg": Decimal(review_avg).quantize(Decimal("0.01")),
        "training_completion_rate": completion_rate,
        "disciplinary_count": disciplinary_count,
    }


def current_user_employee(db: Session, user_id: str) -> Employee | None:
    """Find the employee linked to a user, or by matching email."""
    emp = db.scalar(select(Employee).where(Employee.user_id == user_id))
    if emp:
        return emp
    # fallback: match email
    from app.models.user import User
    user = db.get(User, user_id)
    if user:
        emp = db.scalar(select(Employee).where(Employee.email == user.email))
    return emp
