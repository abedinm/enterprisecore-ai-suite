"""Finance business logic: numbering, totals, tax/payroll math, reports, PDF."""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import (
    CurrencyRate,
    Customer,
    Expense,
    ExpenseCategory,
    Invoice,
)

CENTS = Decimal("0.01")
TWO_DP = Decimal("0.01")


def _q(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


# ---- Invoice numbering ---------------------------------------------------
def next_invoice_number(db: Session) -> str:
    today = date.today()
    prefix = f"INV-{today.year}-"
    count = db.scalar(
        select(func.count(Invoice.id)).where(Invoice.invoice_number.like(f"{prefix}%"))
    ) or 0
    return f"{prefix}{count + 1:05d}"


# ---- Line and total math -------------------------------------------------
def compute_line_total(quantity: Decimal | int | float, unit_price: Decimal | int | float,
                      tax_rate: Decimal | int | float = 0) -> tuple[Decimal, Decimal]:
    """Return (subtotal_for_line, tax_for_line)."""
    sub = (_q(quantity) * _q(unit_price)).quantize(CENTS, rounding=ROUND_HALF_UP)
    tax = (sub * _q(tax_rate)).quantize(CENTS, rounding=ROUND_HALF_UP)
    return sub, tax


def recompute_invoice(invoice: Invoice) -> None:
    """Recalculate subtotal/tax/total from lines + discount."""
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for line in invoice.lines:
        sub, tax = compute_line_total(line.quantity, line.unit_price, line.tax_rate)
        line.line_total = (sub + tax).quantize(CENTS, rounding=ROUND_HALF_UP)
        subtotal += sub
        tax_total += tax
    invoice.subtotal = subtotal.quantize(CENTS, rounding=ROUND_HALF_UP)
    invoice.tax_total = tax_total.quantize(CENTS, rounding=ROUND_HALF_UP)
    discount = _q(invoice.discount_total or 0)
    invoice.discount_total = discount
    invoice.total = (subtotal + tax_total - discount).quantize(CENTS, rounding=ROUND_HALF_UP)


# ---- Payroll math --------------------------------------------------------
PERIOD_FACTORS = {
    "annual": Decimal("1"),
    "monthly": Decimal("12"),
    "biweekly": Decimal("26"),
    "weekly": Decimal("52"),
}


def estimate_payroll(
    gross_salary: Decimal,
    *,
    pay_frequency: str = "monthly",
    tax_rate: Decimal = Decimal("0.22"),
    deductions: Decimal = Decimal("0"),
    bonuses: Decimal = Decimal("0"),
) -> dict[str, Decimal]:
    gross = _q(Decimal(str(gross_salary)) + Decimal(str(bonuses)))
    tax = _q(gross * Decimal(str(tax_rate)))
    deduct = _q(deductions)
    net = _q(gross - tax - deduct)
    return {
        "gross": gross,
        "tax": tax,
        "deductions": deduct,
        "bonuses": _q(bonuses),
        "net": net,
        "frequency": pay_frequency,
    }


# ---- Tax estimator -------------------------------------------------------
DEFAULT_BRACKETS: list[tuple[Decimal, Decimal]] = [
    (Decimal("11000"), Decimal("0.10")),
    (Decimal("44725"), Decimal("0.12")),
    (Decimal("95375"), Decimal("0.22")),
    (Decimal("182100"), Decimal("0.24")),
    (Decimal("231250"), Decimal("0.32")),
    (Decimal("578125"), Decimal("0.35")),
    (Decimal("0"), Decimal("0.37")),
]


def estimate_tax(
    income: Decimal,
    *,
    deductions: Decimal = Decimal("0"),
    brackets: Iterable[tuple[Decimal, Decimal]] | None = None,
) -> dict[str, Decimal]:
    """Brackets: iterable of (threshold, rate). Final bracket with threshold=0 = top marginal rate."""
    taxable = max(_q(income) - _q(deductions), Decimal("0"))
    brackets = list(brackets or DEFAULT_BRACKETS)
    tax = Decimal("0")
    prev_threshold = Decimal("0")
    remaining = taxable
    breakdown: list[dict] = []
    for threshold, rate in brackets:
        band_top = threshold if threshold > 0 else (prev_threshold + remaining)
        band = max(min(remaining, band_top - prev_threshold), Decimal("0"))
        band_tax = (band * rate).quantize(CENTS, rounding=ROUND_HALF_UP)
        tax += band_tax
        if band > 0:
            breakdown.append({
                "from": _q(prev_threshold),
                "to": _q(band_top),
                "rate": Decimal(str(rate)).quantize(Decimal("0.0001")),
                "taxable": _q(band),
                "tax": band_tax,
            })
        prev_threshold = band_top
        remaining -= band
        if remaining <= 0:
            break
    tax_q = _q(tax)
    effective = (tax_q / taxable).quantize(Decimal("0.0001")) if taxable > 0 else Decimal("0")
    return {
        "taxable_income": taxable,
        "estimated_tax": tax_q,
        "effective_rate": effective,
        "breakdown": breakdown,
    }


# ---- Currency conversion -------------------------------------------------
def find_rate(db: Session, base: str, quote: str, as_of: date | None = None) -> Decimal:
    if base == quote:
        return Decimal("1")
    base, quote = base.upper(), quote.upper()
    stmt = (
        select(CurrencyRate)
        .where(CurrencyRate.base_currency == base, CurrencyRate.quote_currency == quote)
        .order_by(CurrencyRate.effective_date.desc())
        .limit(1)
    )
    if as_of:
        stmt = stmt.where(CurrencyRate.effective_date <= as_of)
    row = db.scalar(stmt)
    if row:
        return row.rate
    inv = db.scalar(
        select(CurrencyRate)
        .where(CurrencyRate.base_currency == quote, CurrencyRate.quote_currency == base)
        .order_by(CurrencyRate.effective_date.desc())
        .limit(1)
    )
    if inv and inv.rate > 0:
        return (Decimal("1") / inv.rate).quantize(Decimal("0.00000001"))
    # Triangulate via USD
    if base != "USD" and quote != "USD":
        try:
            a = find_rate(db, base, "USD", as_of)
            b = find_rate(db, "USD", quote, as_of)
            return (a * b).quantize(Decimal("0.00000001"))
        except ValueError:
            pass
    raise ValueError(f"No exchange rate found for {base}->{quote}")


def convert(db: Session, amount: Decimal, base: str, quote: str, as_of: date | None = None) -> dict:
    rate = find_rate(db, base, quote, as_of)
    return {
        "amount": _q(amount),
        "converted": (Decimal(str(amount)) * rate).quantize(CENTS, rounding=ROUND_HALF_UP),
        "rate": rate,
        "from_currency": base.upper(),
        "to_currency": quote.upper(),
        "as_of": as_of or date.today(),
    }


def multi_currency_summary(db: Session) -> dict:
    """Aggregate balances by currency across invoices and expenses."""
    inv_totals = db.execute(
        select(Invoice.currency, Invoice.status, func.coalesce(func.sum(Invoice.total), 0))
        .group_by(Invoice.currency, Invoice.status)
    ).all()
    exp_totals = db.execute(
        select(Expense.currency, func.coalesce(func.sum(Expense.amount), 0))
        .group_by(Expense.currency)
    ).all()
    by_currency: dict[str, dict] = defaultdict(lambda: {
        "invoiced": Decimal("0"),
        "paid": Decimal("0"),
        "outstanding": Decimal("0"),
        "expenses": Decimal("0"),
    })
    for cur, status, total in inv_totals:
        d = by_currency[cur or "USD"]
        d["invoiced"] += Decimal(total)
        if status == "paid":
            d["paid"] += Decimal(total)
        elif status in ("sent", "overdue", "draft"):
            d["outstanding"] += Decimal(total)
    for cur, total in exp_totals:
        by_currency[cur or "USD"]["expenses"] += Decimal(total)
    entries = []
    for cur in sorted(by_currency.keys()):
        d = by_currency[cur]
        entries.append({
            "currency": cur,
            "invoiced": _q(d["invoiced"]),
            "paid": _q(d["paid"]),
            "outstanding": _q(d["outstanding"]),
            "expenses": _q(d["expenses"]),
            "net": _q(d["paid"] - d["expenses"]),
        })
    return {"as_of": date.today(), "currencies": entries}


# ---- Reports -------------------------------------------------------------
def profit_and_loss(db: Session, start: date, end: date) -> dict:
    revenue = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.issue_date.between(start, end), Invoice.status != "void")
    ) or Decimal("0")
    expenses_q = (
        select(ExpenseCategory.name, func.coalesce(func.sum(Expense.amount), 0))
        .select_from(Expense)
        .outerjoin(ExpenseCategory, Expense.category_id == ExpenseCategory.id)
        .where(Expense.date.between(start, end))
        .group_by(ExpenseCategory.name)
    )
    by_category: dict[str, Decimal] = {}
    op_expenses = Decimal("0")
    for name, total in db.execute(expenses_q).all():
        by_category[name or "Uncategorized"] = Decimal(total)
        op_expenses += Decimal(total)
    revenue_d = Decimal(revenue)
    gross_profit = revenue_d  # cogs not modelled separately yet
    net = gross_profit - op_expenses
    return {
        "period_start": start,
        "period_end": end,
        "revenue": _q(revenue_d),
        "cogs": Decimal("0.00"),
        "gross_profit": _q(gross_profit),
        "operating_expenses": _q(op_expenses),
        "net_income": _q(net),
        "by_category": {k: _q(v) for k, v in by_category.items()},
    }


def balance_sheet(db: Session, as_of: date) -> dict:
    ar = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.issue_date <= as_of, Invoice.status.in_(("sent", "overdue", "draft")))
    ) or Decimal("0")
    paid_revenue = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.issue_date <= as_of, Invoice.status == "paid")
    ) or Decimal("0")
    expenses_to_date = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.date <= as_of)
    ) or Decimal("0")
    cash = Decimal(paid_revenue) - Decimal(expenses_to_date)
    total_assets = Decimal(ar) + cash
    return {
        "as_of": as_of,
        "assets": {"accounts_receivable": _q(ar), "cash_equivalents": _q(cash)},
        "liabilities": {"accounts_payable": Decimal("0.00")},
        "equity": {"retained_earnings": _q(total_assets)},
        "totals": {
            "total_assets": _q(total_assets),
            "total_liabilities": Decimal("0.00"),
            "total_equity": _q(total_assets),
        },
    }


def cash_flow(db: Session, start: date, end: date) -> dict:
    months: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"inflow": Decimal("0"), "outflow": Decimal("0")})
    inflows = db.execute(
        select(Invoice.issue_date, func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.issue_date.between(start, end), Invoice.status == "paid")
        .group_by(Invoice.issue_date)
    ).all()
    for d, total in inflows:
        months[d.strftime("%Y-%m")]["inflow"] += Decimal(total)
    outflows = db.execute(
        select(Expense.date, func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.date.between(start, end))
        .group_by(Expense.date)
    ).all()
    for d, total in outflows:
        months[d.strftime("%Y-%m")]["outflow"] += Decimal(total)
    entries = []
    total_in = Decimal("0")
    total_out = Decimal("0")
    for period in sorted(months.keys()):
        inflow = _q(months[period]["inflow"])
        outflow = _q(months[period]["outflow"])
        entries.append({"period": period, "inflow": inflow, "outflow": outflow, "net": _q(inflow - outflow)})
        total_in += inflow
        total_out += outflow
    return {
        "period_start": start,
        "period_end": end,
        "entries": entries,
        "totals": {"inflow": total_in, "outflow": total_out, "net": _q(total_in - total_out)},
    }


def forecast(db: Session, months_ahead: int = 6) -> dict:
    """Simple moving-average forecast based on the last 6 months."""
    end = date.today()
    start = end.replace(day=1) - timedelta(days=180)
    history = cash_flow(db, start, end)["entries"]
    if not history:
        return {"method": "moving_average_6", "months_ahead": months_ahead, "points": [],
                "history": [], "confidence": Decimal("0")}
    avg_in = mean([float(e["inflow"]) for e in history]) if history else 0
    avg_out = mean([float(e["outflow"]) for e in history]) if history else 0
    points = []
    cursor = end.replace(day=1)
    for _ in range(months_ahead):
        cursor = (cursor + timedelta(days=32)).replace(day=1)
        points.append({
            "period": cursor.strftime("%Y-%m"),
            "revenue_forecast": _q(Decimal(str(avg_in))),
            "expense_forecast": _q(Decimal(str(avg_out))),
            "net_forecast": _q(Decimal(str(avg_in - avg_out))),
        })
    return {
        "method": "moving_average_6",
        "months_ahead": months_ahead,
        "history": history,
        "points": points,
        "confidence": Decimal("0.65") if len(history) >= 3 else Decimal("0.30"),
    }


def budget_vs_actual(db: Session, plan, start: date | None = None, end: date | None = None) -> list[dict]:
    """Hydrate budget items with actual expenses from matching category names."""
    from app.models.finance import BudgetItem
    items = db.scalars(select(BudgetItem).where(BudgetItem.budget_plan_id == plan.id)).all()
    results = []
    for item in items:
        cat = db.scalar(select(ExpenseCategory).where(ExpenseCategory.name == item.category))
        actual = Decimal("0")
        if cat:
            stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.category_id == cat.id)
            if start:
                stmt = stmt.where(Expense.date >= start)
            if end:
                stmt = stmt.where(Expense.date <= end)
            actual = Decimal(db.scalar(stmt) or 0)
        planned = Decimal(item.planned_amount or 0)
        results.append({
            "id": item.id,
            "category": item.category,
            "planned": _q(planned),
            "actual": _q(actual),
            "variance": _q(planned - actual),
            "utilization": (actual / planned).quantize(Decimal("0.0001")) if planned > 0 else Decimal("0"),
        })
    return results


# ---- PDF generation ------------------------------------------------------
def _styles():
    return getSampleStyleSheet()


def _header(story: list, title: str, subtitle: str | None = None) -> None:
    styles = _styles()
    story.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    if subtitle:
        story.append(Paragraph(subtitle, styles["BodyText"]))
    story.append(Spacer(1, 6 * mm))


def _amount_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ])


def render_invoice_pdf(invoice: Invoice, customer: Customer | None = None,
                      company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Invoice {invoice.invoice_number}")
    styles = _styles()
    h1 = styles["Title"]
    body = styles["BodyText"]
    small = styles["Italic"]

    story: list = []
    story.append(Paragraph(f"<b>{company_name}</b>", h1))
    story.append(Paragraph(f"Invoice <b>{invoice.invoice_number}</b>", body))
    story.append(Spacer(1, 6 * mm))

    meta = [
        ["Bill to:", customer.name if customer else "—"],
        ["Email:", (customer.email if customer else "") or "—"],
        ["Issue date:", invoice.issue_date.strftime("%Y-%m-%d")],
        ["Due date:", invoice.due_date.strftime("%Y-%m-%d")],
        ["Currency:", invoice.currency],
        ["Status:", invoice.status.upper()],
    ]
    t = Table(meta, colWidths=[35 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    line_data = [["Description", "Qty", "Unit price", "Tax %", "Line total"]]
    for line in invoice.lines:
        line_data.append([
            line.description,
            f"{line.quantity:.2f}",
            f"{invoice.currency} {line.unit_price:.2f}",
            f"{(line.tax_rate * 100):.2f}%",
            f"{invoice.currency} {line.line_total:.2f}",
        ])
    lines_table = Table(line_data, colWidths=[80 * mm, 18 * mm, 28 * mm, 18 * mm, 30 * mm])
    lines_table.setStyle(_amount_table_style())
    story.append(lines_table)
    story.append(Spacer(1, 4 * mm))

    totals = [
        ["Subtotal", f"{invoice.currency} {invoice.subtotal:.2f}"],
        ["Tax", f"{invoice.currency} {invoice.tax_total:.2f}"],
        ["Discount", f"-{invoice.currency} {invoice.discount_total:.2f}"],
        ["Total", f"{invoice.currency} {invoice.total:.2f}"],
    ]
    totals_table = Table(totals, colWidths=[60 * mm, 40 * mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(totals_table)

    if invoice.notes:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(f"<i>{invoice.notes}</i>", small))

    doc.build(story)
    return buffer.getvalue()


def render_pnl_pdf(data: dict, currency: str = "USD",
                   company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Profit & Loss Statement")
    story: list = []
    _header(story, company_name,
            f"Profit &amp; Loss · {data['period_start']} → {data['period_end']}")
    rows = [
        ["Line", f"Amount ({currency})"],
        ["Revenue", f"{data['revenue']:.2f}"],
        ["Cost of goods sold", f"{data['cogs']:.2f}"],
        ["Gross profit", f"{data['gross_profit']:.2f}"],
        ["Operating expenses", f"{data['operating_expenses']:.2f}"],
        ["Net income", f"{data['net_income']:.2f}"],
    ]
    t = Table(rows, colWidths=[110 * mm, 60 * mm])
    t.setStyle(_amount_table_style())
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    cat_rows = [["Expense category", f"Amount ({currency})"]] + [
        [k, f"{v:.2f}"] for k, v in (data.get("by_category") or {}).items()
    ]
    if len(cat_rows) > 1:
        ct = Table(cat_rows, colWidths=[110 * mm, 60 * mm])
        ct.setStyle(_amount_table_style())
        story.append(ct)
    doc.build(story)
    return buffer.getvalue()


def render_balance_sheet_pdf(data: dict, currency: str = "USD",
                             company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Balance Sheet")
    story: list = []
    _header(story, company_name, f"Balance Sheet · As of {data['as_of']}")

    def section(title: str, entries: dict) -> Table:
        rows = [[title, f"Amount ({currency})"]] + [
            [k.replace("_", " ").title(), f"{v:.2f}"] for k, v in entries.items()
        ]
        tt = Table(rows, colWidths=[110 * mm, 60 * mm])
        tt.setStyle(_amount_table_style())
        return tt

    story.append(section("Assets", data["assets"]))
    story.append(Spacer(1, 4 * mm))
    story.append(section("Liabilities", data["liabilities"]))
    story.append(Spacer(1, 4 * mm))
    story.append(section("Equity", data["equity"]))
    story.append(Spacer(1, 4 * mm))
    story.append(section("Totals", data["totals"]))
    doc.build(story)
    return buffer.getvalue()


def render_cash_flow_pdf(data: dict, currency: str = "USD",
                         company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Cash Flow Statement")
    story: list = []
    _header(story, company_name,
            f"Cash Flow · {data['period_start']} → {data['period_end']}")
    rows = [["Period", "Inflow", "Outflow", "Net"]]
    for e in data["entries"]:
        rows.append([
            e["period"],
            f"{currency} {e['inflow']:.2f}",
            f"{currency} {e['outflow']:.2f}",
            f"{currency} {e['net']:.2f}",
        ])
    t = Table(rows, colWidths=[40 * mm, 45 * mm, 45 * mm, 45 * mm])
    t.setStyle(_amount_table_style())
    story.append(t)
    story.append(Spacer(1, 4 * mm))
    totals = data["totals"]
    tot = Table([
        ["Total inflow", f"{currency} {totals['inflow']:.2f}"],
        ["Total outflow", f"{currency} {totals['outflow']:.2f}"],
        ["Net cash flow", f"{currency} {totals['net']:.2f}"],
    ], colWidths=[110 * mm, 60 * mm], hAlign="RIGHT")
    tot.setStyle(TableStyle([
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(tot)
    doc.build(story)
    return buffer.getvalue()


def render_forecast_pdf(data: dict, currency: str = "USD",
                        company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Financial Forecast")
    story: list = []
    _header(story, company_name,
            f"Forecast (method: {data['method']}, horizon: {data['months_ahead']} months)")
    rows = [["Period", "Revenue", "Expense", "Net"]]
    for p in data["points"]:
        rows.append([
            p["period"],
            f"{currency} {p['revenue_forecast']:.2f}",
            f"{currency} {p['expense_forecast']:.2f}",
            f"{currency} {p['net_forecast']:.2f}",
        ])
    t = Table(rows, colWidths=[40 * mm, 45 * mm, 45 * mm, 45 * mm])
    t.setStyle(_amount_table_style())
    story.append(t)
    story.append(Spacer(1, 4 * mm))
    styles = _styles()
    story.append(Paragraph(
        f"<i>Confidence: {(data['confidence'] * 100):.0f}%</i>",
        styles["Italic"],
    ))
    doc.build(story)
    return buffer.getvalue()


def render_dashboard_pdf(summary: dict, currency: str = "USD",
                         company_name: str = "Your Company") -> bytes:
    """Single combined report with KPIs and key tables."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Financial Dashboard")
    story: list = []
    _header(story, company_name,
            f"Financial Dashboard · Generated {summary['generated_at']}")
    kpis = summary["kpis"]
    rows = [["KPI", f"Value ({currency})"]] + [
        ["Total revenue (YTD)", f"{kpis['ytd_revenue']:.2f}"],
        ["Total expenses (YTD)", f"{kpis['ytd_expenses']:.2f}"],
        ["Net income (YTD)", f"{kpis['ytd_net']:.2f}"],
        ["Outstanding receivables", f"{kpis['outstanding']:.2f}"],
        ["Active customers", f"{kpis['active_customers']}"],
        ["Active vendors", f"{kpis['active_vendors']}"],
        ["Open invoices", f"{kpis['open_invoices']}"],
        ["Recurring payments", f"{kpis['recurring_count']}"],
    ]
    t = Table(rows, colWidths=[110 * mm, 60 * mm])
    t.setStyle(_amount_table_style())
    story.append(t)
    doc.build(story)
    return buffer.getvalue()
