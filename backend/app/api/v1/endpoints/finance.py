"""Finance & accounting endpoints — invoices, expenses, payroll, budgets, reports."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.pagination import Page, PaginationParams, paginate
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.finance import (
    BudgetItem,
    BudgetPlan,
    CurrencyRate,
    Customer,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceLine,
    PayrollRun,
    PayslipLine,
    RecurringPayment,
    TaxRate,
    Vendor,
    VendorPayment,
)
from app.models.user import AuditLog, User, UserRole
from app.schemas.finance import (
    BalanceSheetOut,
    BudgetActualRow,
    BudgetAnalyticsOut,
    BudgetItemOut,
    BudgetPlanIn,
    BudgetPlanOut,
    CashFlowOut,
    ConversionIn,
    ConversionOut,
    CurrencyRateIn,
    CurrencyRateOut,
    CustomerIn,
    CustomerOut,
    DashboardKpis,
    DashboardOut,
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    ExpenseIn,
    ExpenseOut,
    ForecastOut,
    InvoiceIn,
    InvoiceOut,
    InvoiceStatusUpdate,
    MultiCurrencyOut,
    PayrollEstimateIn,
    PayrollEstimateOut,
    PayrollRunIn,
    PayrollRunOut,
    PayslipLineOut,
    PnLOut,
    RecurringPaymentIn,
    RecurringPaymentOut,
    TaxEstimateIn,
    TaxEstimateOut,
    TaxRateIn,
    TaxRateOut,
    VendorIn,
    VendorOut,
    VendorPaymentIn,
    VendorPaymentOut,
)
from app.services import finance as fin
from app.services.audit import record_audit

router = APIRouter()


def _audit(db: Session, user: User | None, action: str, entity_type: str,
           entity_id: str | None = None, detail: dict | None = None) -> None:
    record_audit(db, actor=user, action=action, entity_type=entity_type,
                 entity_id=entity_id, detail=detail or {})


def _invoice_to_out(invoice: Invoice) -> dict:
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer_id": invoice.customer_id,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "status": invoice.status,
        "currency": invoice.currency,
        "subtotal": invoice.subtotal,
        "tax_total": invoice.tax_total,
        "discount_total": invoice.discount_total,
        "total": invoice.total,
        "notes": invoice.notes,
        "created_at": invoice.created_at,
        "lines": [
            {
                "id": l.id,
                "description": l.description,
                "quantity": l.quantity,
                "unit_price": l.unit_price,
                "tax_rate": l.tax_rate,
                "line_total": l.line_total,
            }
            for l in invoice.lines
        ],
    }


# ============== Customers ================================================
@router.get("/customers", response_model=list[CustomerOut])
def list_customers(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Legacy unpaginated list (capped at 500). Use ``GET /finance/customers/page`` for paged."""
    stmt = select(Customer).order_by(Customer.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.email.ilike(like)))
    return db.scalars(stmt.limit(500)).all()


@router.get("/customers/page", response_model=Page[CustomerOut])
def list_customers_page(
    q: str | None = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Customer).order_by(Customer.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.email.ilike(like)))
    return paginate(db, stmt, CustomerOut, pagination)


@router.post("/customers", response_model=CustomerOut)
def create_customer(payload: CustomerIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = Customer(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "customer", obj.id, {"name": obj.name})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/customers/{cid}", response_model=CustomerOut)
def update_customer(cid: str, payload: CustomerIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Customer, cid)
    if not obj:
        raise NotFoundError("Customer not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "customer", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/customers/{cid}", status_code=204)
def delete_customer(cid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Customer, cid)
    if obj:
        _audit(db, user, "delete", "customer", obj.id, {"name": obj.name})
        db.delete(obj)
        db.commit()
    return None


# ============== Vendors ==================================================
@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Vendor).order_by(Vendor.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Vendor.name.ilike(like), Vendor.email.ilike(like)))
    return db.scalars(stmt.limit(500)).all()


@router.post("/vendors", response_model=VendorOut)
def create_vendor(payload: VendorIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = Vendor(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "vendor", obj.id, {"name": obj.name})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/vendors/{vid}", response_model=VendorOut)
def update_vendor(vid: str, payload: VendorIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Vendor, vid)
    if not obj:
        raise NotFoundError("Vendor not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "vendor", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/vendors/{vid}", status_code=204)
def delete_vendor(vid: str, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Vendor, vid)
    if obj:
        _audit(db, user, "delete", "vendor", obj.id, {"name": obj.name})
        db.delete(obj)
        db.commit()
    return None


# ============== Invoices =================================================
@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(status: str | None = None, customer_id: str | None = None,
                  db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Legacy unpaginated list (capped at 500). Use ``GET /finance/invoices/page`` for paged."""
    stmt = select(Invoice).order_by(Invoice.issue_date.desc())
    if status:
        stmt = stmt.where(Invoice.status == status)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    invoices = db.scalars(stmt.limit(500)).all()
    return [_invoice_to_out(inv) for inv in invoices]


@router.get("/invoices/page")
def list_invoices_page(
    status: str | None = None,
    customer_id: str | None = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Paginated invoice list. Returns `{items, total, page, page_size, total_pages}`
    where each item has the full nested-lines shape from `_invoice_to_out`."""
    stmt = select(Invoice).order_by(Invoice.issue_date.desc())
    if status:
        stmt = stmt.where(Invoice.status == status)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)

    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    rows = db.scalars(stmt.offset(pagination.offset).limit(pagination.limit)).all()
    items = [_invoice_to_out(inv) for inv in rows]
    from math import ceil
    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_pages": ceil(total / pagination.page_size) if total else 0,
    }


@router.post("/invoices", response_model=InvoiceOut)
def create_invoice(payload: InvoiceIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    number = payload.invoice_number or fin.next_invoice_number(db)
    inv = Invoice(
        invoice_number=number,
        customer_id=payload.customer_id,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        currency=payload.currency,
        notes=payload.notes,
        discount_total=payload.discount_total,
        status="draft",
    )
    for line in payload.lines:
        inv.lines.append(InvoiceLine(**line.model_dump()))
    fin.recompute_invoice(inv)
    db.add(inv)
    db.flush()
    _audit(db, user, "create", "invoice", inv.id, {"number": inv.invoice_number, "total": str(inv.total)})
    db.commit()
    db.refresh(inv)
    return _invoice_to_out(inv)


@router.get("/invoices/{iid}", response_model=InvoiceOut)
def get_invoice(iid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise NotFoundError("Invoice not found")
    return _invoice_to_out(inv)


@router.patch("/invoices/{iid}", response_model=InvoiceOut)
def update_invoice(iid: str, payload: InvoiceIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    inv = db.get(Invoice, iid)
    if not inv:
        raise NotFoundError("Invoice not found")
    inv.customer_id = payload.customer_id
    inv.issue_date = payload.issue_date
    inv.due_date = payload.due_date
    inv.currency = payload.currency
    inv.notes = payload.notes
    inv.discount_total = payload.discount_total
    if payload.invoice_number:
        inv.invoice_number = payload.invoice_number
    inv.lines.clear()
    for line in payload.lines:
        inv.lines.append(InvoiceLine(**line.model_dump()))
    fin.recompute_invoice(inv)
    _audit(db, user, "update", "invoice", inv.id, {"number": inv.invoice_number})
    db.commit()
    db.refresh(inv)
    return _invoice_to_out(inv)


@router.post("/invoices/{iid}/status", response_model=InvoiceOut)
def set_invoice_status(iid: str, payload: InvoiceStatusUpdate, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    inv = db.get(Invoice, iid)
    if not inv:
        raise NotFoundError("Invoice not found")
    valid = {"draft", "sent", "paid", "overdue", "void"}
    if payload.status not in valid:
        raise NotFoundError(f"Invalid status. Allowed: {sorted(valid)}")
    previous = inv.status
    inv.status = payload.status
    _audit(db, user, "status_change", "invoice", inv.id,
           {"from": previous, "to": payload.status, "number": inv.invoice_number})
    db.commit()
    db.refresh(inv)
    return _invoice_to_out(inv)


@router.delete("/invoices/{iid}", status_code=204)
def delete_invoice(iid: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin))):
    inv = db.get(Invoice, iid)
    if inv:
        _audit(db, user, "delete", "invoice", inv.id, {"number": inv.invoice_number})
        db.delete(inv)
        db.commit()
    return None


@router.get("/invoices/{iid}/pdf")
def invoice_pdf(iid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise NotFoundError("Invoice not found")
    customer = db.get(Customer, inv.customer_id) if inv.customer_id else None
    pdf = fin.render_invoice_pdf(inv, customer)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv.invoice_number}.pdf"'},
    )


# ============== Expenses =================================================
@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(start: date | None = None, end: date | None = None,
                  category_id: str | None = None,
                  db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Expense).order_by(Expense.date.desc())
    if start:
        stmt = stmt.where(Expense.date >= start)
    if end:
        stmt = stmt.where(Expense.date <= end)
    if category_id:
        stmt = stmt.where(Expense.category_id == category_id)
    return db.scalars(stmt.limit(1000)).all()


@router.post("/expenses", response_model=ExpenseOut)
def create_expense(payload: ExpenseIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    obj = Expense(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "expense", obj.id, {"amount": str(obj.amount)})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/expenses/{eid}", response_model=ExpenseOut)
def update_expense(eid: str, payload: ExpenseIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    obj = db.get(Expense, eid)
    if not obj:
        raise NotFoundError("Expense not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "expense", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/expenses/{eid}", status_code=204)
def delete_expense(eid: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Expense, eid)
    if obj:
        _audit(db, user, "delete", "expense", obj.id)
        db.delete(obj)
        db.commit()
    return None


@router.get("/expense-categories", response_model=list[ExpenseCategoryOut])
def list_expense_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name)).all()


@router.post("/expense-categories", response_model=ExpenseCategoryOut)
def create_expense_category(payload: ExpenseCategoryIn, db: Session = Depends(get_db),
                            user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = ExpenseCategory(name=payload.name)
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "expense_category", obj.id, {"name": obj.name})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/expense-categories/{cid}", status_code=204)
def delete_expense_category(cid: str, db: Session = Depends(get_db),
                            user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(ExpenseCategory, cid)
    if obj:
        _audit(db, user, "delete", "expense_category", obj.id, {"name": obj.name})
        db.delete(obj)
        db.commit()
    return None


# ============== Payroll ==================================================
@router.post("/payroll/estimate", response_model=PayrollEstimateOut)
def payroll_estimate(payload: PayrollEstimateIn, _: User = Depends(get_current_user)):
    result = fin.estimate_payroll(
        payload.gross_salary,
        pay_frequency=payload.pay_frequency,
        tax_rate=payload.tax_rate,
        deductions=payload.deductions,
        bonuses=payload.bonuses,
    )
    return PayrollEstimateOut(**result)


@router.get("/payroll", response_model=list[PayrollRunOut])
def list_payroll(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(PayrollRun).order_by(PayrollRun.period_end.desc()).limit(200)).all()


@router.get("/payroll/{rid}")
def get_payroll(rid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    run = db.get(PayrollRun, rid)
    if not run:
        raise NotFoundError("Payroll run not found")
    lines = db.scalars(select(PayslipLine).where(PayslipLine.payroll_run_id == rid)).all()
    return {
        "id": run.id,
        "period_start": run.period_start,
        "period_end": run.period_end,
        "status": run.status,
        "gross_total": run.gross_total,
        "deduction_total": run.deduction_total,
        "net_total": run.net_total,
        "lines": [
            {"id": l.id, "employee_id": l.employee_id, "label": l.label,
             "amount": l.amount, "kind": l.kind}
            for l in lines
        ],
    }


@router.post("/payroll", response_model=PayrollRunOut)
def create_payroll(payload: PayrollRunIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    run = PayrollRun(
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    gross = Decimal("0")
    deductions = Decimal("0")
    for line in payload.lines:
        if line.kind in ("earning", "bonus"):
            gross += Decimal(str(line.amount))
        else:
            deductions += Decimal(str(line.amount))
    run.gross_total = gross
    run.deduction_total = deductions
    run.net_total = gross - deductions
    db.add(run)
    db.flush()
    for line in payload.lines:
        db.add(PayslipLine(payroll_run_id=run.id, **line.model_dump()))
    _audit(db, user, "create", "payroll_run", run.id,
           {"period": f"{payload.period_start}..{payload.period_end}",
            "net": str(run.net_total)})
    db.commit()
    db.refresh(run)
    return run


@router.delete("/payroll/{rid}", status_code=204)
def delete_payroll(rid: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(PayrollRun, rid)
    if obj:
        _audit(db, user, "delete", "payroll_run", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Budgets ==================================================
@router.get("/budgets", response_model=list[BudgetPlanOut])
def list_budgets(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    plans = db.scalars(select(BudgetPlan).order_by(BudgetPlan.fiscal_year.desc())).all()
    out = []
    for plan in plans:
        items = db.scalars(select(BudgetItem).where(BudgetItem.budget_plan_id == plan.id)).all()
        out.append(BudgetPlanOut(
            id=plan.id, name=plan.name, fiscal_year=plan.fiscal_year, currency=plan.currency,
            items=[BudgetItemOut.model_validate(i) for i in items],
        ))
    return out


@router.post("/budgets", response_model=BudgetPlanOut)
def create_budget(payload: BudgetPlanIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    plan = BudgetPlan(name=payload.name, fiscal_year=payload.fiscal_year, currency=payload.currency)
    db.add(plan)
    db.flush()
    items = [BudgetItem(budget_plan_id=plan.id, **i.model_dump()) for i in payload.items]
    db.add_all(items)
    _audit(db, user, "create", "budget_plan", plan.id,
           {"name": plan.name, "fiscal_year": plan.fiscal_year})
    db.commit()
    return BudgetPlanOut(
        id=plan.id, name=plan.name, fiscal_year=plan.fiscal_year, currency=plan.currency,
        items=[BudgetItemOut.model_validate(i) for i in items],
    )


@router.patch("/budgets/{bid}", response_model=BudgetPlanOut)
def update_budget(bid: str, payload: BudgetPlanIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    plan = db.get(BudgetPlan, bid)
    if not plan:
        raise NotFoundError("Budget plan not found")
    plan.name = payload.name
    plan.fiscal_year = payload.fiscal_year
    plan.currency = payload.currency
    # replace items
    existing = db.scalars(select(BudgetItem).where(BudgetItem.budget_plan_id == bid)).all()
    for item in existing:
        db.delete(item)
    db.flush()
    items = [BudgetItem(budget_plan_id=plan.id, **i.model_dump()) for i in payload.items]
    db.add_all(items)
    _audit(db, user, "update", "budget_plan", plan.id)
    db.commit()
    return BudgetPlanOut(
        id=plan.id, name=plan.name, fiscal_year=plan.fiscal_year, currency=plan.currency,
        items=[BudgetItemOut.model_validate(i) for i in items],
    )


@router.delete("/budgets/{bid}", status_code=204)
def delete_budget(bid: str, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(UserRole.admin))):
    plan = db.get(BudgetPlan, bid)
    if plan:
        _audit(db, user, "delete", "budget_plan", plan.id, {"name": plan.name})
        db.delete(plan)
        db.commit()
    return None


@router.get("/budgets/{bid}/analytics", response_model=BudgetAnalyticsOut)
def budget_analytics(bid: str, start: date | None = None, end: date | None = None,
                     db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    plan = db.get(BudgetPlan, bid)
    if not plan:
        raise NotFoundError("Budget plan not found")
    rows = fin.budget_vs_actual(db, plan, start=start, end=end)
    planned_total = sum((Decimal(str(r["planned"])) for r in rows), Decimal("0"))
    actual_total = sum((Decimal(str(r["actual"])) for r in rows), Decimal("0"))
    return BudgetAnalyticsOut(
        plan_id=plan.id, name=plan.name, fiscal_year=plan.fiscal_year, currency=plan.currency,
        rows=[BudgetActualRow(**r) for r in rows],
        totals={
            "planned": planned_total,
            "actual": actual_total,
            "variance": planned_total - actual_total,
        },
    )


# ============== Tax ======================================================
@router.get("/tax-rates", response_model=list[TaxRateOut])
def list_tax_rates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(TaxRate).order_by(TaxRate.jurisdiction)).all()


@router.post("/tax-rates", response_model=TaxRateOut)
def create_tax_rate(payload: TaxRateIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = TaxRate(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "tax_rate", obj.id,
           {"jurisdiction": obj.jurisdiction, "rate": str(obj.rate)})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/tax-rates/{rid}", status_code=204)
def delete_tax_rate(rid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(TaxRate, rid)
    if obj:
        _audit(db, user, "delete", "tax_rate", obj.id)
        db.delete(obj)
        db.commit()
    return None


@router.post("/tax/estimate", response_model=TaxEstimateOut)
def tax_estimate(payload: TaxEstimateIn, _: User = Depends(get_current_user)):
    result = fin.estimate_tax(payload.income, deductions=payload.deductions,
                              brackets=payload.brackets or None)
    return TaxEstimateOut(**result)


# ============== Recurring ===============================================
@router.get("/recurring", response_model=list[RecurringPaymentOut])
def list_recurring(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(RecurringPayment).order_by(RecurringPayment.next_due_date)).all()


@router.post("/recurring", response_model=RecurringPaymentOut)
def create_recurring(payload: RecurringPaymentIn, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = RecurringPayment(**payload.model_dump())
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "recurring_payment", obj.id, {"title": obj.title})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/recurring/{rid}", response_model=RecurringPaymentOut)
def update_recurring(rid: str, payload: RecurringPaymentIn, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(RecurringPayment, rid)
    if not obj:
        raise NotFoundError("Recurring payment not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", "recurring_payment", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/recurring/{rid}", status_code=204)
def delete_recurring(rid: str, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(RecurringPayment, rid)
    if obj:
        _audit(db, user, "delete", "recurring_payment", obj.id, {"title": obj.title})
        db.delete(obj)
        db.commit()
    return None


# ============== Vendor Payments =========================================
@router.get("/vendor-payments", response_model=list[VendorPaymentOut])
def list_vendor_payments(vendor_id: str | None = None, status: str | None = None,
                         start: date | None = None, end: date | None = None,
                         db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(VendorPayment).order_by(VendorPayment.payment_date.desc())
    if vendor_id:
        stmt = stmt.where(VendorPayment.vendor_id == vendor_id)
    if status:
        stmt = stmt.where(VendorPayment.status == status)
    if start:
        stmt = stmt.where(VendorPayment.payment_date >= start)
    if end:
        stmt = stmt.where(VendorPayment.payment_date <= end)
    return [
        VendorPaymentOut(
            id=v.id, vendor_id=v.vendor_id, payment_date=v.payment_date,
            amount=v.amount, status=v.status,
        )
        for v in db.scalars(stmt.limit(500)).all()
    ]


@router.post("/vendor-payments", response_model=VendorPaymentOut)
def create_vendor_payment(payload: VendorPaymentIn, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = VendorPayment(
        vendor_id=payload.vendor_id,
        payment_date=payload.payment_date,
        amount=Decimal(str(payload.amount)),
        status=payload.status,
    )
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "vendor_payment", obj.id,
           {"vendor_id": obj.vendor_id, "amount": str(obj.amount)})
    db.commit()
    db.refresh(obj)
    return VendorPaymentOut(
        id=obj.id, vendor_id=obj.vendor_id, payment_date=obj.payment_date,
        amount=obj.amount, status=obj.status,
    )


@router.patch("/vendor-payments/{pid}", response_model=VendorPaymentOut)
def update_vendor_payment(pid: str, payload: VendorPaymentIn, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(VendorPayment, pid)
    if not obj:
        raise NotFoundError("Vendor payment not found")
    obj.vendor_id = payload.vendor_id
    obj.payment_date = payload.payment_date
    obj.amount = Decimal(str(payload.amount))
    obj.status = payload.status
    _audit(db, user, "update", "vendor_payment", obj.id)
    db.commit()
    db.refresh(obj)
    return VendorPaymentOut(
        id=obj.id, vendor_id=obj.vendor_id, payment_date=obj.payment_date,
        amount=obj.amount, status=obj.status,
    )


@router.delete("/vendor-payments/{pid}", status_code=204)
def delete_vendor_payment(pid: str, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(VendorPayment, pid)
    if obj:
        _audit(db, user, "delete", "vendor_payment", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Currency =================================================
@router.get("/currency/rates", response_model=list[CurrencyRateOut])
def list_currency_rates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(CurrencyRate).order_by(CurrencyRate.effective_date.desc()).limit(500)).all()


@router.post("/currency/rates", response_model=CurrencyRateOut)
def create_currency_rate(payload: CurrencyRateIn, db: Session = Depends(get_db),
                         user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = CurrencyRate(
        base_currency=payload.base_currency.upper(),
        quote_currency=payload.quote_currency.upper(),
        rate=payload.rate,
        effective_date=payload.effective_date,
    )
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "currency_rate", obj.id,
           {"pair": f"{obj.base_currency}/{obj.quote_currency}", "rate": str(obj.rate)})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/currency/rates/{rid}", status_code=204)
def delete_currency_rate(rid: str, db: Session = Depends(get_db),
                         user: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(CurrencyRate, rid)
    if obj:
        _audit(db, user, "delete", "currency_rate", obj.id)
        db.delete(obj)
        db.commit()
    return None


@router.post("/currency/convert", response_model=ConversionOut)
def currency_convert(payload: ConversionIn, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    result = fin.convert(db, payload.amount, payload.from_currency,
                         payload.to_currency, payload.as_of)
    return ConversionOut(**result)


@router.get("/currency/summary", response_model=MultiCurrencyOut)
def currency_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return MultiCurrencyOut(**fin.multi_currency_summary(db))


# ============== Reports ==================================================
@router.get("/reports/pnl", response_model=PnLOut)
def pnl(start: date = Query(...), end: date = Query(...),
        db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return PnLOut(**fin.profit_and_loss(db, start, end))


@router.get("/reports/pnl/pdf")
def pnl_pdf(start: date = Query(...), end: date = Query(...),
            currency: str = Query("USD"),
            db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    data = fin.profit_and_loss(db, start, end)
    pdf = fin.render_pnl_pdf(data, currency=currency)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="pnl-{start}-{end}.pdf"'})


@router.get("/reports/balance-sheet", response_model=BalanceSheetOut)
def balance(as_of: date = Query(...), db: Session = Depends(get_db),
            _: User = Depends(get_current_user)):
    return BalanceSheetOut(**fin.balance_sheet(db, as_of))


@router.get("/reports/balance-sheet/pdf")
def balance_pdf(as_of: date = Query(...), currency: str = Query("USD"),
                db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    data = fin.balance_sheet(db, as_of)
    pdf = fin.render_balance_sheet_pdf(data, currency=currency)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="balance-sheet-{as_of}.pdf"'})


@router.get("/reports/cash-flow", response_model=CashFlowOut)
def cashflow(start: date = Query(...), end: date = Query(...),
             db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return CashFlowOut(**fin.cash_flow(db, start, end))


@router.get("/reports/cash-flow/pdf")
def cashflow_pdf(start: date = Query(...), end: date = Query(...),
                 currency: str = Query("USD"),
                 db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    data = fin.cash_flow(db, start, end)
    pdf = fin.render_cash_flow_pdf(data, currency=currency)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="cash-flow-{start}-{end}.pdf"'})


@router.get("/reports/forecast", response_model=ForecastOut)
def forecast_report(months_ahead: int = Query(6, ge=1, le=24),
                    db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return ForecastOut(**fin.forecast(db, months_ahead))


@router.get("/reports/forecast/pdf")
def forecast_pdf(months_ahead: int = Query(6, ge=1, le=24),
                 currency: str = Query("USD"),
                 db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    data = fin.forecast(db, months_ahead)
    pdf = fin.render_forecast_pdf(data, currency=currency)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="forecast-{months_ahead}m.pdf"'})


def _build_dashboard(db: Session) -> DashboardOut:
    today = date.today()
    start = today.replace(month=1, day=1)
    pnl_data = fin.profit_and_loss(db, start, today)
    cash = fin.cash_flow(db, start, today)
    outstanding = Decimal(str(db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.status.in_(("sent", "overdue", "draft")))
    ) or 0))
    active_customers = db.scalar(select(func.count(Customer.id))) or 0
    active_vendors = db.scalar(select(func.count(Vendor.id))) or 0
    open_invoices = db.scalar(
        select(func.count(Invoice.id)).where(Invoice.status.in_(("sent", "draft")))
    ) or 0
    overdue_invoices = db.scalar(
        select(func.count(Invoice.id)).where(Invoice.status == "overdue")
    ) or 0
    recurring_count = db.scalar(select(func.count(RecurringPayment.id))) or 0
    top_customers_rows = db.execute(
        select(Customer.name, func.coalesce(func.sum(Invoice.total), 0))
        .join(Invoice, Invoice.customer_id == Customer.id)
        .where(Invoice.issue_date >= start, Invoice.status != "void")
        .group_by(Customer.name)
        .order_by(func.sum(Invoice.total).desc())
        .limit(5)
    ).all()
    top_vendor_rows = db.execute(
        select(Vendor.name, func.coalesce(func.sum(Expense.amount), 0))
        .join(Expense, Expense.vendor_id == Vendor.id)
        .where(Expense.date >= start)
        .group_by(Vendor.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(5)
    ).all()
    upcoming = db.scalars(
        select(RecurringPayment)
        .where(RecurringPayment.next_due_date.isnot(None))
        .order_by(RecurringPayment.next_due_date)
        .limit(5)
    ).all()

    kpis = DashboardKpis(
        ytd_revenue=pnl_data["revenue"],
        ytd_expenses=pnl_data["operating_expenses"],
        ytd_net=pnl_data["net_income"],
        outstanding=outstanding,
        active_customers=active_customers,
        active_vendors=active_vendors,
        open_invoices=open_invoices,
        overdue_invoices=overdue_invoices,
        recurring_count=recurring_count,
    )
    return DashboardOut(
        generated_at=datetime.now(timezone.utc),
        period_start=start,
        period_end=today,
        kpis=kpis,
        revenue_by_month=cash["entries"],
        expenses_by_category=pnl_data["by_category"],
        top_customers=[{"name": n, "total": Decimal(str(t))} for n, t in top_customers_rows],
        top_vendors=[{"name": n, "total": Decimal(str(t))} for n, t in top_vendor_rows],
        upcoming_recurring=[
            {"id": r.id, "title": r.title, "amount": r.amount,
             "currency": r.currency, "cadence": r.cadence,
             "next_due_date": r.next_due_date}
            for r in upcoming
        ],
    )


@router.get("/reports/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _build_dashboard(db)


@router.get("/reports/dashboard/pdf")
def dashboard_pdf(currency: str = Query("USD"),
                  db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    data = _build_dashboard(db)
    summary = {
        "generated_at": data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        "kpis": data.kpis.model_dump(),
    }
    pdf = fin.render_dashboard_pdf(summary, currency=currency)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="dashboard-{date.today()}.pdf"'})


# ============== Audit Trail ==============================================
@router.get("/audit-trail")
def audit_trail(entity_type: str | None = None,
                action: str | None = None,
                actor_id: str | None = None,
                start: date | None = None,
                end: date | None = None,
                limit: int = Query(200, le=1000),
                db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if start:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))
    if end:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc))
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id, "action": r.action, "entity_type": r.entity_type,
            "entity_id": r.entity_id, "actor_id": r.actor_id,
            "detail": json.loads(r.detail or "{}"), "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/audit-trail/summary")
def audit_summary(db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    finance_entities = (
        "invoice", "expense", "expense_category", "payroll_run", "budget_plan",
        "tax_rate", "vendor", "vendor_payment", "customer", "recurring_payment",
        "currency_rate",
    )
    by_entity_rows = db.execute(
        select(AuditLog.entity_type, func.count(AuditLog.id))
        .where(AuditLog.entity_type.in_(finance_entities))
        .group_by(AuditLog.entity_type)
    ).all()
    by_action_rows = db.execute(
        select(AuditLog.action, func.count(AuditLog.id))
        .where(AuditLog.entity_type.in_(finance_entities))
        .group_by(AuditLog.action)
    ).all()
    total = db.scalar(
        select(func.count(AuditLog.id))
        .where(AuditLog.entity_type.in_(finance_entities))
    ) or 0
    return {
        "total": total,
        "by_entity": {e: c for e, c in by_entity_rows},
        "by_action": {a: c for a, c in by_action_rows},
    }
