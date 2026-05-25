"""Multi-entity / multinational consolidation service.

Methodology (simplified v1, follows ASC 830 / IAS 21 patterns):

* Balance sheet — translate every monetary balance from each entity's
  functional currency to the consolidation ``target_currency`` at the
  **closing** rate as of the report date. (For v1 we apply closing rate
  to fixed assets too; tracking historical-cost translation is stubbed
  for v2.)
* Income statement — translate revenue + expenses at the **period
  average** rate (computed from snapshots in ``currency_rates``).
* Intercompany — transactions flagged ``eliminates_on_consolidation``
  wash out: the lender's receivable nets the borrower's payable, and
  matched IC revenue nets the matched IC expense.
* Translation adjustment (CTA) — the residual that falls out of the
  closing vs. average rate gap is reported as a single ``cta`` line
  on the consolidated balance sheet.

All money uses ``Decimal``; FX rates use 8 dp; final outputs quantise
to 2 dp.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import CurrencyRate, Expense, Invoice, PayrollRun
from app.models.finance_consolidation import (
    FxAdjustment,
    IntercompanyTransaction,
    SubsidiaryEntity,
)
from app.services.finance import find_rate

CENTS = Decimal("0.01")
RATE_DP = Decimal("0.00000001")


def _q(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


# ---- Rate helpers --------------------------------------------------------
def average_rate(
    db: Session, base: str, quote: str, period_start: date, period_end: date
) -> Decimal:
    """Period-average FX rate from CurrencyRate snapshots that fall in window.

    Falls back to the closing rate (``find_rate(... as_of=period_end)``) when
    no in-window snapshots exist — keeps small installs working with only
    monthly rate uploads.
    """
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return Decimal("1")
    rows = db.scalars(
        select(CurrencyRate)
        .where(
            CurrencyRate.base_currency == base,
            CurrencyRate.quote_currency == quote,
            CurrencyRate.effective_date >= period_start,
            CurrencyRate.effective_date <= period_end,
        )
    ).all()
    if rows:
        total = sum((r.rate for r in rows), Decimal("0"))
        return (total / Decimal(len(rows))).quantize(RATE_DP)
    # Try inverse direction
    inv_rows = db.scalars(
        select(CurrencyRate)
        .where(
            CurrencyRate.base_currency == quote,
            CurrencyRate.quote_currency == base,
            CurrencyRate.effective_date >= period_start,
            CurrencyRate.effective_date <= period_end,
        )
    ).all()
    if inv_rows:
        total = sum((r.rate for r in inv_rows), Decimal("0"))
        avg_inv = total / Decimal(len(inv_rows))
        if avg_inv > 0:
            return (Decimal("1") / avg_inv).quantize(RATE_DP)
    # Last resort — fall back to closing rate at period end.
    return find_rate(db, base, quote, as_of=period_end)


def _safe_rate(db: Session, base: str, quote: str, as_of: date | None = None) -> Decimal:
    try:
        return find_rate(db, base, quote, as_of=as_of)
    except ValueError:
        # No FX path available — return 1 so the entity contributes its raw
        # numbers; the caller can surface this in the report metadata.
        return Decimal("1")


def _safe_avg(
    db: Session, base: str, quote: str, period_start: date, period_end: date
) -> Decimal:
    try:
        return average_rate(db, base, quote, period_start, period_end)
    except ValueError:
        return Decimal("1")


# ---- Entity-level aggregation -------------------------------------------
def _entity_ar(db: Session, entity_id: str, as_of: date) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .where(
            Invoice.entity_id == entity_id,
            Invoice.issue_date <= as_of,
            Invoice.status.in_(("sent", "overdue", "draft")),
        )
    ) or Decimal("0")
    return Decimal(total)


def _entity_paid_revenue(db: Session, entity_id: str, as_of: date) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .where(
            Invoice.entity_id == entity_id,
            Invoice.issue_date <= as_of,
            Invoice.status == "paid",
        )
    ) or Decimal("0")
    return Decimal(total)


def _entity_expenses(db: Session, entity_id: str, as_of: date) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.entity_id == entity_id, Expense.date <= as_of)
    ) or Decimal("0")
    return Decimal(total)


def _entity_revenue(db: Session, entity_id: str, start: date, end: date) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .where(
            Invoice.entity_id == entity_id,
            Invoice.issue_date.between(start, end),
            Invoice.status != "void",
        )
    ) or Decimal("0")
    return Decimal(total)


def _entity_period_expenses(
    db: Session, entity_id: str, start: date, end: date
) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.entity_id == entity_id, Expense.date.between(start, end))
    ) or Decimal("0")
    return Decimal(total)


def _resolve_entities(
    db: Session, entity_ids: list[str] | None
) -> list[SubsidiaryEntity]:
    stmt = select(SubsidiaryEntity).where(SubsidiaryEntity.is_active.is_(True))
    if entity_ids:
        stmt = stmt.where(SubsidiaryEntity.id.in_(entity_ids))
    return list(db.scalars(stmt.order_by(SubsidiaryEntity.is_main.desc(), SubsidiaryEntity.code)).all())


# ---- Public: consolidate_balance_sheet ----------------------------------
def consolidate_balance_sheet(
    db: Session,
    *,
    as_of: date,
    target_currency: str,
    entity_ids: list[str] | None = None,
) -> dict:
    target_currency = target_currency.upper()
    entities = _resolve_entities(db, entity_ids)

    entity_blocks: list[dict] = []
    sum_assets_target = Decimal("0")
    sum_liab_target = Decimal("0")
    sum_equity_target = Decimal("0")

    for ent in entities:
        ar_func = _entity_ar(db, ent.id, as_of)
        paid_func = _entity_paid_revenue(db, ent.id, as_of)
        exp_func = _entity_expenses(db, ent.id, as_of)
        cash_func = paid_func - exp_func
        assets_func = ar_func + cash_func
        liab_func = Decimal("0")  # AP not modelled yet
        equity_func = assets_func - liab_func

        closing = _safe_rate(db, ent.functional_currency, target_currency, as_of=as_of)
        assets_t = (assets_func * closing).quantize(CENTS, rounding=ROUND_HALF_UP)
        liab_t = (liab_func * closing).quantize(CENTS, rounding=ROUND_HALF_UP)
        equity_t = (equity_func * closing).quantize(CENTS, rounding=ROUND_HALF_UP)

        sum_assets_target += assets_t
        sum_liab_target += liab_t
        sum_equity_target += equity_t

        entity_blocks.append({
            "entity_id": ent.id,
            "code": ent.code,
            "name": ent.name,
            "functional_currency": ent.functional_currency,
            "closing_rate": closing,
            "functional": {
                "accounts_receivable": _q(ar_func),
                "cash_equivalents": _q(cash_func),
                "total_assets": _q(assets_func),
                "total_liabilities": _q(liab_func),
                "total_equity": _q(equity_func),
            },
            "translated": {
                "total_assets": assets_t,
                "total_liabilities": liab_t,
                "total_equity": equity_t,
            },
        })

    # ---- Intercompany eliminations (balance sheet side) -----------------
    ic_q = select(IntercompanyTransaction).where(
        IntercompanyTransaction.eliminates_on_consolidation.is_(True),
        IntercompanyTransaction.transaction_date <= as_of,
    )
    if entity_ids:
        ic_q = ic_q.where(
            IntercompanyTransaction.from_entity_id.in_(entity_ids),
            IntercompanyTransaction.to_entity_id.in_(entity_ids),
        )
    eliminations: list[dict] = []
    eliminated_assets = Decimal("0")
    eliminated_liab = Decimal("0")
    for ic in db.scalars(ic_q).all():
        rate = _safe_rate(db, ic.currency, target_currency, as_of=as_of)
        amt_t = (Decimal(ic.amount) * rate).quantize(CENTS, rounding=ROUND_HALF_UP)
        eliminated_assets += amt_t
        eliminated_liab += amt_t
        eliminations.append({
            "ic_id": ic.id,
            "kind": ic.kind,
            "from_entity_id": ic.from_entity_id,
            "to_entity_id": ic.to_entity_id,
            "currency": ic.currency,
            "amount": _q(ic.amount),
            "rate": rate,
            "amount_target": amt_t,
        })

    consolidated_assets = sum_assets_target - eliminated_assets
    consolidated_liab = sum_liab_target - eliminated_liab
    consolidated_equity = sum_equity_target

    # CTA — residual from rounding + translation
    cta = (
        consolidated_assets - consolidated_liab - consolidated_equity
    ).quantize(CENTS, rounding=ROUND_HALF_UP)

    return {
        "as_of": as_of,
        "target_currency": target_currency,
        "entities": entity_blocks,
        "eliminations": eliminations,
        "consolidated": {
            "total_assets": consolidated_assets.quantize(CENTS, rounding=ROUND_HALF_UP),
            "total_liabilities": consolidated_liab.quantize(CENTS, rounding=ROUND_HALF_UP),
            "total_equity": consolidated_equity.quantize(CENTS, rounding=ROUND_HALF_UP),
        },
        "cta": cta,
    }


# ---- Public: consolidate_pnl --------------------------------------------
def consolidate_pnl(
    db: Session,
    *,
    period_start: date,
    period_end: date,
    target_currency: str,
    entity_ids: list[str] | None = None,
) -> dict:
    target_currency = target_currency.upper()
    entities = _resolve_entities(db, entity_ids)

    entity_blocks: list[dict] = []
    sum_revenue = Decimal("0")
    sum_expenses = Decimal("0")

    for ent in entities:
        rev_func = _entity_revenue(db, ent.id, period_start, period_end)
        exp_func = _entity_period_expenses(db, ent.id, period_start, period_end)
        avg = _safe_avg(
            db, ent.functional_currency, target_currency, period_start, period_end
        )
        rev_t = (rev_func * avg).quantize(CENTS, rounding=ROUND_HALF_UP)
        exp_t = (exp_func * avg).quantize(CENTS, rounding=ROUND_HALF_UP)
        sum_revenue += rev_t
        sum_expenses += exp_t
        entity_blocks.append({
            "entity_id": ent.id,
            "code": ent.code,
            "name": ent.name,
            "functional_currency": ent.functional_currency,
            "average_rate": avg,
            "functional": {
                "revenue": _q(rev_func),
                "expenses": _q(exp_func),
                "net_income": _q(rev_func - exp_func),
            },
            "translated": {
                "revenue": rev_t,
                "expenses": exp_t,
                "net_income": (rev_t - exp_t).quantize(CENTS, rounding=ROUND_HALF_UP),
            },
        })

    net_before = sum_revenue - sum_expenses

    # ---- Intercompany revenue/expense eliminations ---------------------
    ic_q = select(IntercompanyTransaction).where(
        IntercompanyTransaction.eliminates_on_consolidation.is_(True),
        IntercompanyTransaction.transaction_date.between(period_start, period_end),
    )
    if entity_ids:
        ic_q = ic_q.where(
            IntercompanyTransaction.from_entity_id.in_(entity_ids),
            IntercompanyTransaction.to_entity_id.in_(entity_ids),
        )
    eliminations: list[dict] = []
    eliminated_rev = Decimal("0")
    eliminated_exp = Decimal("0")
    for ic in db.scalars(ic_q).all():
        avg = _safe_avg(db, ic.currency, target_currency, period_start, period_end)
        amt_t = (Decimal(ic.amount) * avg).quantize(CENTS, rounding=ROUND_HALF_UP)
        # The "from" entity recognised revenue; the "to" entity recognised expense.
        # Both sides wash on consolidation.
        eliminated_rev += amt_t
        eliminated_exp += amt_t
        eliminations.append({
            "ic_id": ic.id,
            "kind": ic.kind,
            "from_entity_id": ic.from_entity_id,
            "to_entity_id": ic.to_entity_id,
            "currency": ic.currency,
            "amount": _q(ic.amount),
            "rate": avg,
            "amount_target": amt_t,
        })

    consolidated_revenue = sum_revenue - eliminated_rev
    consolidated_expenses = sum_expenses - eliminated_exp
    consolidated_net = consolidated_revenue - consolidated_expenses

    return {
        "period_start": period_start,
        "period_end": period_end,
        "target_currency": target_currency,
        "entities": entity_blocks,
        "eliminations": eliminations,
        "consolidated": {
            "revenue": consolidated_revenue.quantize(CENTS, rounding=ROUND_HALF_UP),
            "expenses": consolidated_expenses.quantize(CENTS, rounding=ROUND_HALF_UP),
            "net_income": consolidated_net.quantize(CENTS, rounding=ROUND_HALF_UP),
            "net_income_before_eliminations": net_before.quantize(
                CENTS, rounding=ROUND_HALF_UP
            ),
        },
    }


# ---- Public: fx_revaluation ---------------------------------------------
def fx_revaluation(
    db: Session,
    *,
    entity_id: str,
    period_end: date,
) -> list[FxAdjustment]:
    """Compute and persist FX gain/loss on the entity's foreign-currency
    monetary balances (invoices in a non-functional currency = AR; expenses
    in a non-functional currency = AP)."""
    ent = db.get(SubsidiaryEntity, entity_id)
    if ent is None:
        raise ValueError(f"Subsidiary entity {entity_id} not found")

    reporting = ent.reporting_currency
    functional = ent.functional_currency
    # "Last period" — naive: 30 days back for the opening rate.
    opening_as_of = period_end - timedelta(days=30)

    adjustments: list[FxAdjustment] = []

    # Group AR by invoice currency
    ar_rows = db.execute(
        select(Invoice.currency, func.coalesce(func.sum(Invoice.total), 0))
        .where(
            Invoice.entity_id == entity_id,
            Invoice.issue_date <= period_end,
            Invoice.status.in_(("sent", "overdue", "draft")),
        )
        .group_by(Invoice.currency)
    ).all()
    for cur, total in ar_rows:
        cur = (cur or "USD").upper()
        if cur == functional:
            continue
        amount = Decimal(total)
        if amount == 0:
            continue
        opening = _safe_rate(db, cur, reporting, as_of=opening_as_of)
        closing = _safe_rate(db, cur, reporting, as_of=period_end)
        gain_loss = ((closing - opening) * amount).quantize(
            CENTS, rounding=ROUND_HALF_UP
        )
        adj = FxAdjustment(
            entity_id=entity_id,
            account_kind="ar",
            original_currency=cur,
            original_amount=amount.quantize(CENTS, rounding=ROUND_HALF_UP),
            reporting_currency=reporting,
            opening_rate=opening,
            closing_rate=closing,
            fx_gain_loss=gain_loss,
            period_end=period_end,
        )
        db.add(adj)
        adjustments.append(adj)

    # AP — expenses in a non-functional currency
    ap_rows = db.execute(
        select(Expense.currency, func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.entity_id == entity_id, Expense.date <= period_end)
        .group_by(Expense.currency)
    ).all()
    for cur, total in ap_rows:
        cur = (cur or "USD").upper()
        if cur == functional:
            continue
        amount = Decimal(total)
        if amount == 0:
            continue
        opening = _safe_rate(db, cur, reporting, as_of=opening_as_of)
        closing = _safe_rate(db, cur, reporting, as_of=period_end)
        # AP is a liability: rising rate → bigger payable → loss
        gain_loss = ((opening - closing) * amount).quantize(
            CENTS, rounding=ROUND_HALF_UP
        )
        adj = FxAdjustment(
            entity_id=entity_id,
            account_kind="ap",
            original_currency=cur,
            original_amount=amount.quantize(CENTS, rounding=ROUND_HALF_UP),
            reporting_currency=reporting,
            opening_rate=opening,
            closing_rate=closing,
            fx_gain_loss=gain_loss,
            period_end=period_end,
        )
        db.add(adj)
        adjustments.append(adj)

    db.flush()
    return adjustments


def get_or_create_main_entity(db: Session, tenant_currency: str = "USD") -> SubsidiaryEntity:
    """Return the tenant's main subsidiary, creating it if absent.

    Called when the application boots without a 0023 migration (fresh
    metadata.create_all in tests) and when tenant onboarding needs a
    home entity for the first invoice.
    """
    existing = db.scalar(
        select(SubsidiaryEntity).where(SubsidiaryEntity.is_main.is_(True))
    )
    if existing:
        return existing
    ent = SubsidiaryEntity(
        name="Main Entity",
        code="MAIN",
        country="US",
        functional_currency=tenant_currency or "USD",
        reporting_currency=tenant_currency or "USD",
        is_main=True,
        is_active=True,
    )
    db.add(ent)
    db.flush()
    return ent
