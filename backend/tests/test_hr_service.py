"""Service-level HR tests — covers org tree, payslip aggregation, payslip PDF,
attendance summary, leave balance, and analytics helpers.

Target: raise app/services/hr.py coverage from 31% toward 80%+.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.finance import PayrollRun, PayslipLine
from app.models.hr import (
    AttendanceRecord,
    Candidate,
    DisciplinaryRecord,
    Employee,
    JobOpening,
    LeaveRequest,
    OnboardingTask,
    OrgUnit,
    PerformanceReview,
    TrainingRecord,
)
from app.services import hr as hr_svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sfx() -> str:
    return uuid.uuid4().hex[:8]


def _emp(sfx: str, dept: str = "Engineering", status: str = "active",
         salary: Decimal = Decimal("5000")) -> Employee:
    return Employee(
        employee_code=f"EC-{sfx}",    # unique required field
        full_name=f"Emp_{sfx}",
        email=f"emp-{sfx}@hr.test",
        department=dept,
        status=status,
        salary=salary,
        hire_date=date.today() - timedelta(days=365),
    )


# ---------------------------------------------------------------------------
# build_org_tree
# ---------------------------------------------------------------------------

def test_build_org_tree_no_crash(session_factory):
    """build_org_tree must not raise even when the DB is empty of units."""
    with session_factory() as db:
        tree = hr_svc.build_org_tree(db)
    assert isinstance(tree, list)


def test_build_org_tree_parent_child(session_factory):
    sfx = _sfx()
    with session_factory() as db:
        parent = OrgUnit(name=f"Eng_{sfx}")
        db.add(parent)
        db.flush()
        child = OrgUnit(name=f"Backend_{sfx}", parent_id=parent.id)
        db.add(child)
        db.commit()

        tree = hr_svc.build_org_tree(db)

    parent_node = next((n for n in tree if n["name"] == f"Eng_{sfx}"), None)
    assert parent_node is not None, "parent unit not found in tree"
    child_names = [c["name"] for c in parent_node["children"]]
    assert f"Backend_{sfx}" in child_names


def test_build_org_tree_headcount(session_factory):
    sfx = _sfx()
    with session_factory() as db:
        unit = OrgUnit(name=f"Sales_{sfx}")
        db.add(unit)
        db.flush()
        # Two employees in this department
        db.add(_emp(sfx + "a", dept=f"Sales_{sfx}"))
        db.add(_emp(sfx + "b", dept=f"Sales_{sfx}"))
        db.commit()

        tree = hr_svc.build_org_tree(db)

    node = next((n for n in tree if n["name"] == f"Sales_{sfx}"), None)
    assert node is not None
    assert node["headcount"] == 2


def test_build_org_tree_manager_name(session_factory):
    sfx = _sfx()
    with session_factory() as db:
        emp = _emp(sfx, dept=f"Ops_{sfx}")
        db.add(emp)
        db.flush()
        unit = OrgUnit(name=f"Ops_{sfx}", manager_employee_id=emp.id)
        db.add(unit)
        db.commit()

        tree = hr_svc.build_org_tree(db)

    node = next((n for n in tree if n["name"] == f"Ops_{sfx}"), None)
    assert node is not None
    assert node["manager_name"] == emp.full_name


# ---------------------------------------------------------------------------
# employee_payslips
# ---------------------------------------------------------------------------

def test_employee_payslips_empty(session_factory):
    sfx = _sfx()
    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.commit()
        result = hr_svc.employee_payslips(db, emp.id)
    assert result == []


def test_employee_payslips_with_data(session_factory):
    sfx = _sfx()
    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.flush()

        run = PayrollRun(
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            status="approved",
        )
        db.add(run)
        db.flush()

        db.add(PayslipLine(payroll_run_id=run.id, employee_id=emp.id,
                           label="Base salary", kind="earning", amount=Decimal("5000")))
        db.add(PayslipLine(payroll_run_id=run.id, employee_id=emp.id,
                           label="Performance bonus", kind="bonus", amount=Decimal("500")))
        db.add(PayslipLine(payroll_run_id=run.id, employee_id=emp.id,
                           label="Income tax", kind="tax", amount=Decimal("1100")))
        db.add(PayslipLine(payroll_run_id=run.id, employee_id=emp.id,
                           label="Health deduction", kind="deduction", amount=Decimal("200")))
        db.commit()

        result = hr_svc.employee_payslips(db, emp.id)

    assert len(result) == 1
    slip = result[0]
    assert slip["payroll_run_id"] == run.id
    assert slip["employee_id"] == emp.id
    assert slip["employee_name"] == emp.full_name
    assert slip["gross"] == Decimal("5500")      # 5000 + 500
    assert slip["deductions"] == Decimal("1300")  # 1100 + 200
    assert slip["net"] == Decimal("4200")
    assert len(slip["lines"]) == 4


def test_employee_payslips_sorted_by_period_desc(session_factory):
    """Multiple runs should come back most-recent first."""
    sfx = _sfx()
    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.flush()

        for month in (3, 4, 5):
            run = PayrollRun(
                period_start=date(2026, month, 1),
                period_end=date(2026, month, 28),
                status="approved",
            )
            db.add(run)
            db.flush()
            db.add(PayslipLine(payroll_run_id=run.id, employee_id=emp.id,
                               label="Base", kind="earning", amount=Decimal("4000")))
        db.commit()

        result = hr_svc.employee_payslips(db, emp.id)

    assert len(result) == 3
    # Most recent period_end first
    assert result[0]["period_end"] > result[1]["period_end"] > result[2]["period_end"]


# ---------------------------------------------------------------------------
# render_payslip_pdf
# ---------------------------------------------------------------------------

def test_render_payslip_pdf_returns_pdf():
    payslip = {
        "employee_name": "Alice Tester",
        "employee_id": "emp-abc",
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 5, 31),
        "gross": Decimal("6000.00"),
        "deductions": Decimal("1200.00"),
        "net": Decimal("4800.00"),
        "currency": "USD",
        "lines": [
            {"label": "Base salary", "kind": "earning", "amount": Decimal("6000")},
            {"label": "Income tax",  "kind": "tax",     "amount": Decimal("1200")},
        ],
    }
    pdf = hr_svc.render_payslip_pdf(payslip, company_name="TestCorp")
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_render_payslip_pdf_no_lines():
    """render_payslip_pdf with an empty lines list and None employee_name."""
    payslip = {
        "employee_name": None,
        "employee_id": "emp-xyz",
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 1, 31),
        "gross": Decimal("0.00"),
        "deductions": Decimal("0.00"),
        "net": Decimal("0.00"),
        "currency": "EUR",
        "lines": [],
    }
    pdf = hr_svc.render_payslip_pdf(payslip)
    assert pdf[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# attendance_summary
# ---------------------------------------------------------------------------

def test_attendance_summary_empty(session_factory):
    sfx = _sfx()
    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.commit()
        result = hr_svc.attendance_summary(db, emp.id)

    assert result["days_present"] == 0
    assert result["hours_total"] == Decimal("0")
    assert result["last_clock_in"] is None


def test_attendance_summary_with_records(session_factory):
    sfx = _sfx()
    tz = timezone.utc
    today = date.today()

    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.flush()

        # Day 1: 8 hours
        db.add(AttendanceRecord(
            employee_id=emp.id,
            clock_in=datetime(today.year, today.month, today.day, 9, 0, tzinfo=tz),
            clock_out=datetime(today.year, today.month, today.day, 17, 0, tzinfo=tz),
        ))
        # Day 2: 7.5 hours (yesterday)
        yesterday = today - timedelta(days=1)
        db.add(AttendanceRecord(
            employee_id=emp.id,
            clock_in=datetime(yesterday.year, yesterday.month, yesterday.day, 9, 0, tzinfo=tz),
            clock_out=datetime(yesterday.year, yesterday.month, yesterday.day, 16, 30, tzinfo=tz),
        ))
        # In-progress record — no clock_out, contributes a distinct day but zero hours
        db.add(AttendanceRecord(
            employee_id=emp.id,
            clock_in=datetime(today.year, today.month, today.day, 8, 0, tzinfo=tz),
            clock_out=None,
        ))
        db.commit()

        result = hr_svc.attendance_summary(db, emp.id)

    # 2 distinct calendar days (today + yesterday)
    assert result["days_present"] == 2
    # today: 8h. yesterday: 7.5h. in-progress: no hours counted
    assert result["hours_total"] == Decimal("15.5")
    assert result["last_clock_in"] is not None


# ---------------------------------------------------------------------------
# leave_balance
# ---------------------------------------------------------------------------

def test_leave_balance_empty(session_factory):
    sfx = _sfx()
    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.commit()
        result = hr_svc.leave_balance(db, emp.id)

    assert result["total_taken"] == 0
    assert result["by_type"] == {}


def test_leave_balance_approved_leaves(session_factory):
    sfx = _sfx()
    today = date.today()

    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.flush()

        # 5-day annual leave (start → start+4 = 5 days inclusive)
        db.add(LeaveRequest(
            employee_id=emp.id, leave_type="annual",
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=6),
            status="approved",
        ))
        # 2-day sick leave
        db.add(LeaveRequest(
            employee_id=emp.id, leave_type="sick",
            start_date=today - timedelta(days=3),
            end_date=today - timedelta(days=2),
            status="approved",
        ))
        db.commit()

        result = hr_svc.leave_balance(db, emp.id)

    assert result["by_type"]["annual"] == 5
    assert result["by_type"]["sick"] == 2
    assert result["total_taken"] == 7


def test_leave_balance_excludes_pending_and_rejected(session_factory):
    sfx = _sfx()
    today = date.today()

    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.flush()

        db.add(LeaveRequest(
            employee_id=emp.id, leave_type="annual",
            start_date=today - timedelta(days=5),
            end_date=today - timedelta(days=3),
            status="pending",
        ))
        db.add(LeaveRequest(
            employee_id=emp.id, leave_type="annual",
            start_date=today - timedelta(days=2),
            end_date=today - timedelta(days=1),
            status="rejected",
        ))
        db.commit()

        result = hr_svc.leave_balance(db, emp.id)

    assert result["total_taken"] == 0


def test_leave_balance_empty_string_type_defaults_to_general(session_factory):
    """leave_type='' (empty string, falsy) must be bucketed as 'general'."""
    sfx = _sfx()
    today = date.today()

    with session_factory() as db:
        emp = _emp(sfx)
        db.add(emp)
        db.flush()

        # Empty string is truthy at the column level but falsy in Python logic
        db.add(LeaveRequest(
            employee_id=emp.id, leave_type="",
            start_date=today - timedelta(days=2),
            end_date=today - timedelta(days=1),
            status="approved",
        ))
        db.commit()

        result = hr_svc.leave_balance(db, emp.id)

    assert "general" in result["by_type"]
    assert result["by_type"]["general"] == 2


# ---------------------------------------------------------------------------
# hr_analytics
# ---------------------------------------------------------------------------

def test_hr_analytics_shape(session_factory):
    """The analytics dict must always contain the expected keys."""
    with session_factory() as db:
        result = hr_svc.hr_analytics(db)

    expected_keys = {
        "headcount", "active", "on_leave", "by_department", "avg_salary",
        "open_positions", "candidates_in_pipeline", "pending_leave_requests",
        "by_status", "hires_by_month", "review_avg", "training_completion_rate",
        "disciplinary_count",
    }
    assert expected_keys <= result.keys()


def test_hr_analytics_with_data(session_factory):
    sfx = _sfx()
    today = date.today()

    with session_factory() as db:
        # Seed three employees
        emp1 = _emp(sfx + "1", dept=f"Dept_{sfx}", status="active")
        emp2 = _emp(sfx + "2", dept=f"Dept_{sfx}", status="active")
        emp3 = _emp(sfx + "3", dept=f"Other_{sfx}", status="on_leave")
        db.add_all([emp1, emp2, emp3])
        db.flush()

        db.add(JobOpening(title=f"Dev_{sfx}", status="open"))
        db.add(Candidate(full_name=f"Cand_{sfx}", stage="applied"))
        db.add(PerformanceReview(
            employee_id=emp1.id, period=f"2026-Q1_{sfx}", score=Decimal("4.0"),
        ))
        db.add(TrainingRecord(
            employee_id=emp1.id, course_name=f"TRN_{sfx}", status="completed",
        ))
        db.add(DisciplinaryRecord(
            employee_id=emp1.id, incident_date=today,
            severity="minor", notes="test",
        ))
        db.commit()

        result = hr_svc.hr_analytics(db)

    # Shared DB — assert minimums (≥ what we seeded)
    assert result["headcount"] >= 3
    assert result["active"] >= 2
    assert result["on_leave"] >= 1
    assert result["open_positions"] >= 1
    assert result["candidates_in_pipeline"] >= 1
    assert result["disciplinary_count"] >= 1
    assert f"Dept_{sfx}" in result["by_department"]
