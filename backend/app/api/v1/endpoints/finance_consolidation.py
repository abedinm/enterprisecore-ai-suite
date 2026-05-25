"""Multi-entity consolidation endpoints.

Mounted under ``/finance`` so the surface sits next to the existing
finance routes — entities, intercompany transactions, consolidated
balance sheet + P&L, and FX revaluation.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.db.session import get_db
from app.models.finance import Expense, Invoice, PayrollRun
from app.models.finance_consolidation import (
    FxAdjustment,
    IntercompanyTransaction,
    SubsidiaryEntity,
)
from app.models.user import User, UserRole
from app.schemas.finance_consolidation import (
    ConsolidatedBalanceSheetOut,
    ConsolidatedPnLOut,
    FxAdjustmentOut,
    FxRevaluationIn,
    IntercompanyTransactionIn,
    IntercompanyTransactionOut,
    SubsidiaryEntityIn,
    SubsidiaryEntityOut,
    SubsidiaryEntityPatch,
)
from app.services import consolidation as consol
from app.services.audit import record_audit

router = APIRouter()


def _audit(db, user, action, entity_type, entity_id=None, detail=None):
    record_audit(
        db, actor=user, action=action, entity_type=entity_type,
        entity_id=entity_id, detail=detail or {},
    )


# ============== Subsidiary entities ======================================
@router.get("/entities", response_model=list[SubsidiaryEntityOut])
def list_entities(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.scalars(
            select(SubsidiaryEntity).order_by(
                SubsidiaryEntity.is_main.desc(), SubsidiaryEntity.code
            )
        ).all()
    )


@router.post("/entities", response_model=SubsidiaryEntityOut)
def create_entity(
    payload: SubsidiaryEntityIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    if payload.is_main:
        # Only one main entity per tenant.
        existing_main = db.scalar(
            select(SubsidiaryEntity).where(SubsidiaryEntity.is_main.is_(True))
        )
        if existing_main:
            raise ConflictError("A main entity already exists for this tenant")
    obj = SubsidiaryEntity(
        name=payload.name,
        code=payload.code,
        country=payload.country.upper(),
        functional_currency=payload.functional_currency.upper(),
        reporting_currency=payload.reporting_currency.upper(),
        parent_entity_id=payload.parent_entity_id,
        is_main=payload.is_main,
        inception_date=payload.inception_date,
        is_active=payload.is_active,
    )
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "subsidiary_entity", obj.id,
           {"code": obj.code, "name": obj.name})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/entities/{eid}", response_model=SubsidiaryEntityOut)
def update_entity(
    eid: str,
    payload: SubsidiaryEntityPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    obj = db.get(SubsidiaryEntity, eid)
    if not obj:
        raise NotFoundError("Entity not found")
    data = payload.model_dump(exclude_unset=True)
    for key in ("country", "functional_currency", "reporting_currency"):
        if data.get(key):
            data[key] = data[key].upper()
    for k, v in data.items():
        setattr(obj, k, v)
    _audit(db, user, "update", "subsidiary_entity", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/entities/{eid}", status_code=204)
def delete_entity(
    eid: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    obj = db.get(SubsidiaryEntity, eid)
    if not obj:
        return None
    # Block deletion when any transaction still references this entity.
    inv_count = db.scalar(
        select(func.count(Invoice.id)).where(Invoice.entity_id == eid)
    ) or 0
    exp_count = db.scalar(
        select(func.count(Expense.id)).where(Expense.entity_id == eid)
    ) or 0
    payroll_count = db.scalar(
        select(func.count(PayrollRun.id)).where(PayrollRun.entity_id == eid)
    ) or 0
    ic_count = db.scalar(
        select(func.count(IntercompanyTransaction.id)).where(
            (IntercompanyTransaction.from_entity_id == eid)
            | (IntercompanyTransaction.to_entity_id == eid)
        )
    ) or 0
    if inv_count + exp_count + payroll_count + ic_count > 0:
        raise ConflictError("Cannot delete entity that still has transactions; deactivate it instead (is_active=false)")
    _audit(db, user, "delete", "subsidiary_entity", obj.id, {"code": obj.code})
    db.delete(obj)
    db.commit()
    return None


# ============== Intercompany transactions ================================
@router.get("/intercompany", response_model=list[IntercompanyTransactionOut])
def list_intercompany(
    from_entity_id: str | None = None,
    to_entity_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(IntercompanyTransaction).order_by(
        IntercompanyTransaction.transaction_date.desc()
    )
    if from_entity_id:
        stmt = stmt.where(IntercompanyTransaction.from_entity_id == from_entity_id)
    if to_entity_id:
        stmt = stmt.where(IntercompanyTransaction.to_entity_id == to_entity_id)
    return list(db.scalars(stmt.limit(500)).all())


@router.post("/intercompany", response_model=IntercompanyTransactionOut)
def create_intercompany(
    payload: IntercompanyTransactionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    if payload.from_entity_id == payload.to_entity_id:
        raise ValidationFailed("from_entity_id and to_entity_id must differ")
    # Both entities must belong to the current tenant — the tenant auto-filter
    # already enforces this via db.get.
    if db.get(SubsidiaryEntity, payload.from_entity_id) is None:
        raise NotFoundError("from_entity not found in this tenant")
    if db.get(SubsidiaryEntity, payload.to_entity_id) is None:
        raise NotFoundError("to_entity not found in this tenant")
    obj = IntercompanyTransaction(
        from_entity_id=payload.from_entity_id,
        to_entity_id=payload.to_entity_id,
        kind=payload.kind,
        amount=Decimal(str(payload.amount)),
        currency=payload.currency.upper(),
        transaction_date=payload.transaction_date,
        description=payload.description,
        eliminates_on_consolidation=payload.eliminates_on_consolidation,
        matched_invoice_id=payload.matched_invoice_id,
    )
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "intercompany_transaction", obj.id,
           {"from": obj.from_entity_id, "to": obj.to_entity_id,
            "kind": obj.kind, "amount": str(obj.amount)})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/intercompany/{tid}", status_code=204)
def delete_intercompany(
    tid: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    obj = db.get(IntercompanyTransaction, tid)
    if obj:
        _audit(db, user, "delete", "intercompany_transaction", obj.id)
        db.delete(obj)
        db.commit()
    return None


# ============== Consolidation reports ====================================
@router.post("/consolidate/balance-sheet", response_model=ConsolidatedBalanceSheetOut)
def consolidate_balance_sheet(
    as_of: date = Query(...),
    target_currency: str = Query("USD"),
    entity_ids: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = consol.consolidate_balance_sheet(
        db, as_of=as_of, target_currency=target_currency, entity_ids=entity_ids
    )
    return ConsolidatedBalanceSheetOut(**result)


@router.post("/consolidate/pnl", response_model=ConsolidatedPnLOut)
def consolidate_pnl(
    period_start: date = Query(...),
    period_end: date = Query(...),
    target_currency: str = Query("USD"),
    entity_ids: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = consol.consolidate_pnl(
        db, period_start=period_start, period_end=period_end,
        target_currency=target_currency, entity_ids=entity_ids,
    )
    return ConsolidatedPnLOut(**result)


# ============== FX revaluation ===========================================
@router.post("/fx-revaluation", response_model=list[FxAdjustmentOut])
def run_fx_revaluation(
    payload: FxRevaluationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    try:
        adjustments = consol.fx_revaluation(
            db, entity_id=payload.entity_id, period_end=payload.period_end
        )
    except ValueError as e:
        raise NotFoundError(str(e)) from e
    _audit(db, user, "fx_revaluation", "subsidiary_entity", payload.entity_id,
           {"period_end": payload.period_end.isoformat(),
            "adjustments": len(adjustments)})
    db.commit()
    return adjustments


@router.get("/fx-revaluation", response_model=list[FxAdjustmentOut])
def list_fx_adjustments(
    entity_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(FxAdjustment).order_by(FxAdjustment.period_end.desc())
    if entity_id:
        stmt = stmt.where(FxAdjustment.entity_id == entity_id)
    return list(db.scalars(stmt.limit(500)).all())
