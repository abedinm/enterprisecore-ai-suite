"""Student finance — owner-isolated records + public scholarship board.

Workflow features layered on top of the CRUD scaffold:
- ``GET /finance/students/me/summary`` — current-month rollup with savings rate.
- ``GET /finance/students/me/trend`` — last N months income/expense/net for charts.
- ``POST /finance/budgets`` (+ list/patch/delete) — student-owned monthly
  category budgets.
- ``GET /finance/students/me/budget-status`` — current spending vs each budget.
- ``GET /finance/scholarships/upcoming`` — scholarships with deadlines in the
  next N days.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    REGISTRAR_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.db.session import get_db
from app.models.academic.finance import (
    AcademicScholarship, AcademicStudentBudget, AcademicStudentFinanceRecord,
)
from app.models.user import User
from app.schemas.academic.finance import (
    BudgetCreate, BudgetOut, BudgetStatusOut, BudgetStatusRow, BudgetUpdate,
    FinanceCategoryTotal, FinanceTrend, MonthlySummary, ScholarshipCreate,
    ScholarshipOut, ScholarshipUpdate, StudentFinanceCreate, StudentFinanceOut,
    StudentFinanceUpdate, TrendPoint,
)

router = APIRouter()


def _parse_month(month: str) -> tuple[date, date]:
    """Return (first-of-month, first-of-next-month) for an inclusive/exclusive
    range. Used by every endpoint that takes a ``month=YYYY-MM`` query."""
    try:
        year_s, month_s = month.split("-")
        year, month_num = int(year_s), int(month_s)
        first = date(year, month_num, 1)
    except (ValueError, IndexError) as exc:
        raise ValidationFailed(
            "month must be YYYY-MM (e.g. 2026-05)",
        ) from exc
    if month_num == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month_num + 1, 1)
    return first, next_first


def _records_for_student_in_window(
    db: Session, *, student_id: str, start: date, end_exclusive: date,
):
    return db.scalars(
        select(AcademicStudentFinanceRecord)
        .where(
            AcademicStudentFinanceRecord.student_id == student_id,
            AcademicStudentFinanceRecord.occurred_on >= start,
            AcademicStudentFinanceRecord.occurred_on < end_exclusive,
        )
    ).all()


# ---------------------------------------------------------------------------
# Per-student records (owner isolated — student sees only own rows)
# ---------------------------------------------------------------------------
@router.get("/records", response_model=list[StudentFinanceOut])
def list_records(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return db.scalars(
        select(AcademicStudentFinanceRecord)
        .where(AcademicStudentFinanceRecord.student_id == current.id)
        .order_by(AcademicStudentFinanceRecord.occurred_on.desc())
    ).all()


@router.post(
    "/records",
    response_model=StudentFinanceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_record(
    payload: StudentFinanceCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = AcademicStudentFinanceRecord(
        student_id=current.id, **payload.model_dump()
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Dashboard views — declared BEFORE /records/{record_id} so the dynamic id
# segment doesn't capture them.
# ---------------------------------------------------------------------------
@router.get(
    "/students/me/summary",
    response_model=MonthlySummary,
)
def my_monthly_summary(
    month: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Total allowance, scholarship, loan, expense + net + savings rate for
    a calendar month. ``month`` defaults to the current month in UTC."""
    if month is None:
        today = datetime.now(timezone.utc).date()
        month = f"{today.year:04d}-{today.month:02d}"
    start, end_excl = _parse_month(month)
    rows = _records_for_student_in_window(
        db, student_id=current.id, start=start, end_exclusive=end_excl,
    )
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    currency = "USD"
    for r in rows:
        totals[r.kind] += r.amount
        if r.kind == "expense":
            by_category[r.category or ""] += r.amount
        if r.currency:
            currency = r.currency
    income = (
        totals["allowance"] + totals["scholarship"] + totals["loan"]
    )
    expense = totals["expense"]
    net = income - expense
    savings_rate = float(
        (income - expense) / income
    ) if income > 0 else 0.0
    return MonthlySummary(
        month=month,
        currency=currency,
        total_allowance=totals["allowance"],
        total_scholarship=totals["scholarship"],
        total_loan=totals["loan"],
        total_expense=expense,
        net=net,
        savings_rate=round(max(min(savings_rate, 1.0), -10.0), 4),
        expense_by_category=[
            FinanceCategoryTotal(category=k, amount=v)
            for k, v in sorted(by_category.items())
        ],
    )


def _month_iter(end: date, months: int):
    """Yield (year, month) tuples ending on ``end``'s month, ``months`` long.

    Used by the trend endpoint to build a contiguous tail-of-history window
    even when some months had zero activity (those still show as 0/0/0).
    """
    year, month = end.year, end.month
    out: list[tuple[int, int]] = []
    for _ in range(months):
        out.append((year, month))
        # Walk backwards a month at a time.
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
    out.reverse()
    return out


@router.get(
    "/students/me/trend",
    response_model=FinanceTrend,
)
def my_finance_trend(
    months: int = 6,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Income/expense/net per month over the last N months (inclusive of now)."""
    months = max(1, min(months, 24))
    today = datetime.now(timezone.utc).date()
    months_window = _month_iter(today, months)
    first_year, first_month = months_window[0]
    window_start = date(first_year, first_month, 1)
    rows = db.scalars(
        select(AcademicStudentFinanceRecord)
        .where(
            AcademicStudentFinanceRecord.student_id == current.id,
            AcademicStudentFinanceRecord.occurred_on >= window_start,
        )
    ).all()
    bucket: dict[str, tuple[Decimal, Decimal]] = {}
    for y, m in months_window:
        bucket[f"{y:04d}-{m:02d}"] = (Decimal("0"), Decimal("0"))
    currency = "USD"
    for r in rows:
        key = f"{r.occurred_on.year:04d}-{r.occurred_on.month:02d}"
        if key not in bucket:
            continue
        income, expense = bucket[key]
        if r.kind in {"allowance", "scholarship", "loan"}:
            income += r.amount
        elif r.kind == "expense":
            expense += r.amount
        bucket[key] = (income, expense)
        if r.currency:
            currency = r.currency
    points = [
        TrendPoint(
            month=key,
            income=income,
            expense=expense,
            net=income - expense,
        )
        for key, (income, expense) in bucket.items()
    ]
    return FinanceTrend(currency=currency, points=points)


@router.get(
    "/students/me/budget-status",
    response_model=BudgetStatusOut,
)
def my_budget_status(
    month: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Current-month spending vs each budget the student has set."""
    if month is None:
        today = datetime.now(timezone.utc).date()
        month = f"{today.year:04d}-{today.month:02d}"
    start, end_excl = _parse_month(month)
    budgets = db.scalars(
        select(AcademicStudentBudget)
        .where(AcademicStudentBudget.student_id == current.id)
    ).all()
    spent_by_cat: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    currency = "USD"
    for r in _records_for_student_in_window(
        db, student_id=current.id, start=start, end_exclusive=end_excl,
    ):
        if r.kind == "expense":
            spent_by_cat[r.category or ""] += r.amount
            if r.currency:
                currency = r.currency
    rows: list[BudgetStatusRow] = []
    for b in sorted(budgets, key=lambda x: x.category):
        spent = spent_by_cat.get(b.category, Decimal("0"))
        remaining = b.monthly_limit - spent
        over = spent > b.monthly_limit
        over_by = (spent - b.monthly_limit) if over else Decimal("0")
        rows.append(BudgetStatusRow(
            category=b.category,
            monthly_limit=b.monthly_limit,
            spent=spent,
            remaining=remaining,
            over_budget=over,
            over_by=over_by,
        ))
    return BudgetStatusOut(month=month, currency=currency, rows=rows)


# ---------------------------------------------------------------------------
# Budgets — student-owned CRUD
# ---------------------------------------------------------------------------
@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return db.scalars(
        select(AcademicStudentBudget)
        .where(AcademicStudentBudget.student_id == current.id)
        .order_by(AcademicStudentBudget.category)
    ).all()


@router.post(
    "/budgets",
    response_model=BudgetOut,
    status_code=status.HTTP_201_CREATED,
)
def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Create a per-student per-category budget. The unique constraint catches
    duplicates at the DB layer; we surface that as a 409 with a clear message."""
    existing = db.scalar(
        select(AcademicStudentBudget).where(
            and_(
                AcademicStudentBudget.student_id == current.id,
                AcademicStudentBudget.category == payload.category,
            )
        )
    )
    if existing is not None:
        raise ConflictError(
            f"A budget for '{payload.category}' already exists; PATCH it instead.",
        )
    obj = AcademicStudentBudget(
        student_id=current.id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/budgets/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: str,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudentBudget, budget_id, "Budget")
    if obj.student_id != current.id:
        raise NotFoundError("Budget not found")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT,
)
def delete_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudentBudget, budget_id, "Budget")
    if obj.student_id != current.id:
        raise NotFoundError("Budget not found")
    db.delete(obj)
    db.commit()


@router.get("/records/{record_id}", response_model=StudentFinanceOut)
def get_record(
    record_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudentFinanceRecord, record_id, "Record")
    if obj.student_id != current.id:
        raise NotFoundError("Record not found")
    return obj


@router.patch("/records/{record_id}", response_model=StudentFinanceOut)
def update_record(
    record_id: str, payload: StudentFinanceUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudentFinanceRecord, record_id, "Record")
    if obj.student_id != current.id:
        raise NotFoundError("Record not found")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT,
)
def delete_record(
    record_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudentFinanceRecord, record_id, "Record")
    if obj.student_id != current.id:
        raise NotFoundError("Record not found")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Scholarship board (public read; registrar/admin write)
# ---------------------------------------------------------------------------
@router.get(
    "/scholarships/upcoming",
    response_model=list[ScholarshipOut],
)
def upcoming_scholarships(
    days: int = 60,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Scholarships with deadlines in the next ``days`` days (inclusive of today)."""
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=max(1, min(days, 365)))
    return db.scalars(
        select(AcademicScholarship)
        .where(
            AcademicScholarship.deadline.is_not(None),
            AcademicScholarship.deadline >= today,
            AcademicScholarship.deadline <= cutoff,
        )
        .order_by(AcademicScholarship.deadline)
    ).all()


@router.get("/scholarships", response_model=list[ScholarshipOut])
def list_scholarships(db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    return db.scalars(
        select(AcademicScholarship).order_by(
            AcademicScholarship.deadline.asc().nullslast()
        )
    ).all()


@router.post(
    "/scholarships",
    response_model=ScholarshipOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def create_scholarship(payload: ScholarshipCreate,
                       db: Session = Depends(get_db)):
    obj = AcademicScholarship(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/scholarships/{scholarship_id}",
    response_model=ScholarshipOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def update_scholarship(
    scholarship_id: str, payload: ScholarshipUpdate,
    db: Session = Depends(get_db),
):
    obj = _get_or_404(db, AcademicScholarship, scholarship_id, "Scholarship")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/scholarships/{scholarship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def delete_scholarship(scholarship_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicScholarship, scholarship_id, "Scholarship")
    db.delete(obj)
    db.commit()
