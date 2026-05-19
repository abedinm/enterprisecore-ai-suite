"""CRM & sales endpoints."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from secrets import token_hex

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.crm import (
    CommunicationEntry, Contact, Contract, CustomerSegment, Deal, EmailCampaign,
    FollowUp, Lead, Proposal, Quotation,
)
from app.models.user import User, UserRole
from app.schemas.crm import (
    CommunicationIn, CommunicationOut, ContactIn, ContactOut, ContractIn,
    ContractOut, CustomerSegmentIn, CustomerSegmentOut, DealIn, DealOut,
    DealStageUpdate, EmailCampaignIn, EmailCampaignOut, FollowUpIn, FollowUpOut,
    LeadIn, LeadOut, ProposalIn, ProposalOut, QuotationIn, QuotationOut,
    SalesAnalyticsOut, SalesForecastOut,
)

router = APIRouter()


def _crud(model, db, payload, item_id=None):
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


# ---- Contacts -----------------------------------------------------------
@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Contact).order_by(Contact.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Contact.name.ilike(like), Contact.company.ilike(like), Contact.email.ilike(like)))
    return db.scalars(stmt.limit(1000)).all()


@router.post("/contacts", response_model=ContactOut)
def create_contact(payload: ContactIn, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    return _crud(Contact, db, payload)


@router.patch("/contacts/{cid}", response_model=ContactOut)
def update_contact(cid: str, payload: ContactIn, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    return _crud(Contact, db, payload, item_id=cid)


@router.delete("/contacts/{cid}", status_code=204)
def delete_contact(cid: str, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Contact, cid)
    if obj:
        db.delete(obj)
        db.commit()


# ---- Leads --------------------------------------------------------------
@router.get("/leads", response_model=list[LeadOut])
def list_leads(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Lead).order_by(Lead.score.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    return db.scalars(stmt.limit(1000)).all()


@router.post("/leads", response_model=LeadOut)
def create_lead(payload: LeadIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _crud(Lead, db, payload)


@router.patch("/leads/{lid}", response_model=LeadOut)
def update_lead(lid: str, payload: LeadIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _crud(Lead, db, payload, item_id=lid)


# ---- Deals (pipeline) ---------------------------------------------------
PIPELINE_STAGES = ["qualified", "discovery", "proposal", "negotiation", "won", "lost"]


@router.get("/deals", response_model=list[DealOut])
def list_deals(stage: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Deal).order_by(Deal.created_at.desc())
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    return db.scalars(stmt.limit(1000)).all()


@router.get("/deals/pipeline")
def deal_pipeline(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    deals = db.scalars(select(Deal).order_by(Deal.created_at.desc())).all()
    columns: dict[str, list] = {s: [] for s in PIPELINE_STAGES}
    for d in deals:
        columns.setdefault(d.stage, []).append({
            "id": d.id, "title": d.title, "value": str(d.value), "probability": str(d.probability),
            "expected_close_date": d.expected_close_date.isoformat() if d.expected_close_date else None,
            "contact_id": d.contact_id,
        })
    return {"stages": [{"stage": s, "deals": columns[s]} for s in PIPELINE_STAGES]}


@router.post("/deals", response_model=DealOut)
def create_deal(payload: DealIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _crud(Deal, db, payload)


@router.patch("/deals/{did}", response_model=DealOut)
def update_deal(did: str, payload: DealIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _crud(Deal, db, payload, item_id=did)


@router.post("/deals/{did}/stage", response_model=DealOut)
def update_deal_stage(did: str, payload: DealStageUpdate, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    deal = db.get(Deal, did)
    if not deal:
        raise NotFoundError("Deal not found")
    deal.stage = payload.stage
    db.commit()
    db.refresh(deal)
    return deal


# ---- Follow-ups & Communications ----------------------------------------
@router.get("/follow-ups", response_model=list[FollowUpOut])
def list_follow_ups(open_only: bool = True, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(FollowUp).order_by(FollowUp.due_at)
    if open_only:
        stmt = stmt.where(FollowUp.status == "open")
    return db.scalars(stmt.limit(500)).all()


@router.post("/follow-ups", response_model=FollowUpOut)
def create_follow_up(payload: FollowUpIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _crud(FollowUp, db, payload)


@router.post("/follow-ups/{fid}/complete", response_model=FollowUpOut)
def complete_follow_up(fid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.get(FollowUp, fid)
    if not obj:
        raise NotFoundError("Follow-up not found")
    obj.status = "completed"
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/communications", response_model=list[CommunicationOut])
def list_communications(contact_id: str | None = None, db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)):
    stmt = select(CommunicationEntry).order_by(CommunicationEntry.created_at.desc())
    if contact_id:
        stmt = stmt.where(CommunicationEntry.contact_id == contact_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/communications", response_model=CommunicationOut)
def log_communication(payload: CommunicationIn, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    return _crud(CommunicationEntry, db, payload)


# ---- Contracts, Proposals, Quotations -----------------------------------
@router.get("/contracts", response_model=list[ContractOut])
def list_contracts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Contract).order_by(Contract.created_at.desc())).all()


@router.post("/contracts", response_model=ContractOut)
def create_contract(payload: ContractIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Contract, db, payload)


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Proposal).order_by(Proposal.created_at.desc())).all()


@router.post("/proposals", response_model=ProposalOut)
def create_proposal(payload: ProposalIn, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    return _crud(Proposal, db, payload)


@router.get("/quotations", response_model=list[QuotationOut])
def list_quotations(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Quotation).order_by(Quotation.created_at.desc())).all()


@router.post("/quotations", response_model=QuotationOut)
def create_quotation(payload: QuotationIn, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("quote_number"):
        data["quote_number"] = f"Q-{date.today().year}-{token_hex(3).upper()}"
    obj = Quotation(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Campaigns & Segments -----------------------------------------------
@router.get("/campaigns", response_model=list[EmailCampaignOut])
def list_campaigns(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(EmailCampaign).order_by(EmailCampaign.created_at.desc())).all()


@router.post("/campaigns", response_model=EmailCampaignOut)
def create_campaign(payload: EmailCampaignIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(EmailCampaign, db, payload)


@router.get("/segments", response_model=list[CustomerSegmentOut])
def list_segments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(CustomerSegment).order_by(CustomerSegment.name)).all()


@router.post("/segments", response_model=CustomerSegmentOut)
def create_segment(payload: CustomerSegmentIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(CustomerSegment, db, payload)


# ---- Analytics ----------------------------------------------------------
@router.get("/analytics", response_model=SalesAnalyticsOut)
def sales_analytics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    pipeline_q = (
        select(Deal.stage, func.coalesce(func.sum(Deal.value), 0), func.count(Deal.id))
        .group_by(Deal.stage)
    )
    by_stage: dict[str, int] = {}
    pipeline_total = Decimal("0")
    weighted = Decimal("0")
    won = Decimal("0")
    lost = Decimal("0")
    for stage, total, count in db.execute(pipeline_q).all():
        by_stage[stage] = count
        if stage == "won":
            won += Decimal(total)
        elif stage == "lost":
            lost += Decimal(total)
        else:
            pipeline_total += Decimal(total)
    # Weighted pipeline = sum(deal.value * probability/100) for open deals
    open_deals = db.scalars(select(Deal).where(~Deal.stage.in_(("won", "lost")))).all()
    for d in open_deals:
        weighted += Decimal(d.value) * (Decimal(d.probability) / Decimal("100"))

    lead_rows = db.execute(select(Lead.status, func.count(Lead.id)).group_by(Lead.status)).all()
    follow_ups = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.status == "open")) or 0
    return SalesAnalyticsOut(
        pipeline_value=pipeline_total,
        weighted_pipeline=weighted,
        deals_by_stage=by_stage,
        won_value=won,
        lost_value=lost,
        lead_count_by_status={s: c for s, c in lead_rows},
        open_follow_ups=follow_ups,
    )


@router.get("/forecast", response_model=SalesForecastOut)
def sales_forecast(months_ahead: int = 6, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    today = date.today()
    months_data = []
    for i in range(months_ahead):
        month_start = (today.replace(day=1) + timedelta(days=32 * (i + 1))).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        deals = db.scalars(
            select(Deal).where(
                Deal.expected_close_date.between(month_start, month_end - timedelta(days=1)),
                ~Deal.stage.in_(("won", "lost")),
            )
        ).all()
        expected = sum((Decimal(d.value) * Decimal(d.probability) / Decimal("100") for d in deals), Decimal("0"))
        months_data.append({
            "period": month_start.strftime("%Y-%m"),
            "expected_revenue": str(expected.quantize(Decimal("0.01"))),
            "deal_count": len(deals),
        })
    return SalesForecastOut(months=months_data, method="probability_weighted")
