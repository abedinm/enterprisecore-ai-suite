"""CRM & sales endpoints — 12 tools with audit logging."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Response
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
from app.services import crm as crm_svc
from app.services.audit import record_audit

router = APIRouter()


def _audit(db: Session, user: User | None, action: str, entity_type: str,
           entity_id: str | None = None, detail: dict | None = None) -> None:
    record_audit(db, actor=user, action=action, entity_type=entity_type,
                 entity_id=entity_id, detail=detail or {})


def _create(model, db, payload, user, entity_type, *, name_key="title"):
    obj = model(**payload.model_dump())
    db.add(obj)
    db.flush()
    detail = {}
    if hasattr(obj, name_key):
        detail[name_key] = getattr(obj, name_key)
    _audit(db, user, "create", entity_type, obj.id, detail)
    db.commit()
    db.refresh(obj)
    return obj


def _update(model, db, payload, item_id, user, entity_type):
    obj = db.get(model, item_id)
    if not obj:
        raise NotFoundError(f"{model.__name__} not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    _audit(db, user, "update", entity_type, obj.id)
    db.commit()
    db.refresh(obj)
    return obj


def _delete(model, db, item_id, user, entity_type):
    obj = db.get(model, item_id)
    if obj:
        _audit(db, user, "delete", entity_type, obj.id)
        db.delete(obj)
        db.commit()


# ============== Contacts (Customers) =====================================
@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(q: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(Contact).order_by(Contact.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Contact.name.ilike(like), Contact.company.ilike(like),
                              Contact.email.ilike(like)))
    return db.scalars(stmt.limit(1000)).all()


@router.post("/contacts", response_model=ContactOut)
def create_contact(payload: ContactIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return _create(Contact, db, payload, user, "contact", name_key="name")


@router.patch("/contacts/{cid}", response_model=ContactOut)
def update_contact(cid: str, payload: ContactIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return _update(Contact, db, payload, cid, user, "contact")


@router.delete("/contacts/{cid}", status_code=204)
def delete_contact(cid: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    _delete(Contact, db, cid, user, "contact")
    return None


# ============== Leads ====================================================
@router.get("/leads", response_model=list[LeadOut])
def list_leads(status: str | None = None, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    stmt = select(Lead).order_by(Lead.score.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    return db.scalars(stmt.limit(1000)).all()


@router.post("/leads", response_model=LeadOut)
def create_lead(payload: LeadIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return _create(Lead, db, payload, user, "lead", name_key="source")


@router.patch("/leads/{lid}", response_model=LeadOut)
def update_lead(lid: str, payload: LeadIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return _update(Lead, db, payload, lid, user, "lead")


@router.delete("/leads/{lid}", status_code=204)
def delete_lead(lid: str, db: Session = Depends(get_db),
                user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    _delete(Lead, db, lid, user, "lead")
    return None


@router.post("/leads/{lid}/convert", response_model=DealOut)
def convert_lead(lid: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Promote a lead to a deal."""
    lead = db.get(Lead, lid)
    if not lead:
        raise NotFoundError("Lead not found")
    contact = db.get(Contact, lead.contact_id) if lead.contact_id else None
    deal = Deal(
        contact_id=lead.contact_id,
        title=f"Lead from {contact.name if contact else lead.source or 'unknown'}",
        stage="qualified",
        value=Decimal("0"),
        probability=Decimal("20"),
    )
    db.add(deal)
    lead.status = "converted"
    db.flush()
    _audit(db, user, "convert", "lead", lead.id, {"deal_id": deal.id})
    db.commit()
    db.refresh(deal)
    return deal


# ============== Deals & Pipeline =========================================
PIPELINE_STAGES = ["qualified", "discovery", "proposal", "negotiation", "won", "lost"]


@router.get("/deals", response_model=list[DealOut])
def list_deals(stage: str | None = None, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
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
            "id": d.id, "title": d.title, "value": str(d.value),
            "probability": str(d.probability),
            "expected_close_date": d.expected_close_date.isoformat() if d.expected_close_date else None,
            "contact_id": d.contact_id,
        })
    return {"stages": [{"stage": s, "deals": columns[s]} for s in PIPELINE_STAGES]}


@router.post("/deals", response_model=DealOut)
def create_deal(payload: DealIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return _create(Deal, db, payload, user, "deal", name_key="title")


@router.patch("/deals/{did}", response_model=DealOut)
def update_deal(did: str, payload: DealIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return _update(Deal, db, payload, did, user, "deal")


@router.post("/deals/{did}/stage", response_model=DealOut)
def update_deal_stage(did: str, payload: DealStageUpdate, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    deal = db.get(Deal, did)
    if not deal:
        raise NotFoundError("Deal not found")
    previous = deal.stage
    deal.stage = payload.stage
    _audit(db, user, "stage_change", "deal", deal.id,
           {"from": previous, "to": payload.stage, "title": deal.title})
    db.commit()
    db.refresh(deal)
    return deal


@router.delete("/deals/{did}", status_code=204)
def delete_deal(did: str, db: Session = Depends(get_db),
                user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    _delete(Deal, db, did, user, "deal")
    return None


# ============== Follow-ups ===============================================
@router.get("/follow-ups", response_model=list[FollowUpOut])
def list_follow_ups(open_only: bool = True, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(FollowUp).order_by(FollowUp.due_at)
    if open_only:
        stmt = stmt.where(FollowUp.status == "open")
    return db.scalars(stmt.limit(500)).all()


@router.post("/follow-ups", response_model=FollowUpOut)
def create_follow_up(payload: FollowUpIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return _create(FollowUp, db, payload, user, "follow_up", name_key="notes")


@router.post("/follow-ups/{fid}/complete", response_model=FollowUpOut)
def complete_follow_up(fid: str, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    obj = db.get(FollowUp, fid)
    if not obj:
        raise NotFoundError("Follow-up not found")
    obj.status = "completed"
    _audit(db, user, "complete", "follow_up", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/follow-ups/{fid}", status_code=204)
def delete_follow_up(fid: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    _delete(FollowUp, db, fid, user, "follow_up")
    return None


# ============== Communications ===========================================
@router.get("/communications", response_model=list[CommunicationOut])
def list_communications(contact_id: str | None = None, db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)):
    stmt = select(CommunicationEntry).order_by(CommunicationEntry.created_at.desc())
    if contact_id:
        stmt = stmt.where(CommunicationEntry.contact_id == contact_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/communications", response_model=CommunicationOut)
def log_communication(payload: CommunicationIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    return _create(CommunicationEntry, db, payload, user, "communication", name_key="channel")


@router.delete("/communications/{cid}", status_code=204)
def delete_communication(cid: str, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    _delete(CommunicationEntry, db, cid, user, "communication")
    return None


# ============== Contracts ================================================
@router.get("/contracts", response_model=list[ContractOut])
def list_contracts(status: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(Contract).order_by(Contract.created_at.desc())
    if status:
        stmt = stmt.where(Contract.status == status)
    return db.scalars(stmt).all()


@router.post("/contracts", response_model=ContractOut)
def create_contract(payload: ContractIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _create(Contract, db, payload, user, "contract", name_key="title")


@router.patch("/contracts/{cid}", response_model=ContractOut)
def update_contract(cid: str, payload: ContractIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _update(Contract, db, payload, cid, user, "contract")


@router.delete("/contracts/{cid}", status_code=204)
def delete_contract(cid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin))):
    _delete(Contract, db, cid, user, "contract")
    return None


# ============== Proposals ================================================
@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(status: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(Proposal).order_by(Proposal.created_at.desc())
    if status:
        stmt = stmt.where(Proposal.status == status)
    return db.scalars(stmt).all()


@router.post("/proposals", response_model=ProposalOut)
def create_proposal(payload: ProposalIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return _create(Proposal, db, payload, user, "proposal", name_key="title")


@router.patch("/proposals/{pid}", response_model=ProposalOut)
def update_proposal(pid: str, payload: ProposalIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return _update(Proposal, db, payload, pid, user, "proposal")


@router.delete("/proposals/{pid}", status_code=204)
def delete_proposal(pid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    _delete(Proposal, db, pid, user, "proposal")
    return None


@router.get("/proposals/{pid}/pdf")
def proposal_pdf(pid: str, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    p = db.get(Proposal, pid)
    if not p:
        raise NotFoundError("Proposal not found")
    contact = db.get(Contact, p.contact_id) if p.contact_id else None
    pdf = crm_svc.render_proposal_pdf(p, contact)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="proposal-{p.id[:8]}.pdf"'})


# ============== Quotations ================================================
@router.get("/quotations", response_model=list[QuotationOut])
def list_quotations(status: str | None = None, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(Quotation).order_by(Quotation.created_at.desc())
    if status:
        stmt = stmt.where(Quotation.status == status)
    return db.scalars(stmt).all()


@router.post("/quotations", response_model=QuotationOut)
def create_quotation(payload: QuotationIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("quote_number"):
        data["quote_number"] = crm_svc.generate_quote_number()
    obj = Quotation(**data)
    db.add(obj)
    db.flush()
    _audit(db, user, "create", "quotation", obj.id, {"number": obj.quote_number})
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/quotations/{qid}", response_model=QuotationOut)
def update_quotation(qid: str, payload: QuotationIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return _update(Quotation, db, payload, qid, user, "quotation")


@router.delete("/quotations/{qid}", status_code=204)
def delete_quotation(qid: str, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    _delete(Quotation, db, qid, user, "quotation")
    return None


@router.get("/quotations/{qid}/pdf")
def quote_pdf(qid: str, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    q = db.get(Quotation, qid)
    if not q:
        raise NotFoundError("Quotation not found")
    contact = db.get(Contact, q.contact_id) if q.contact_id else None
    pdf = crm_svc.render_quote_pdf(q, contact)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{q.quote_number}.pdf"'})


# ============== Campaigns ================================================
@router.get("/campaigns", response_model=list[EmailCampaignOut])
def list_campaigns(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(EmailCampaign).order_by(EmailCampaign.created_at.desc())).all()


@router.post("/campaigns", response_model=EmailCampaignOut)
def create_campaign(payload: EmailCampaignIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _create(EmailCampaign, db, payload, user, "campaign", name_key="name")


@router.patch("/campaigns/{cid}", response_model=EmailCampaignOut)
def update_campaign(cid: str, payload: EmailCampaignIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _update(EmailCampaign, db, payload, cid, user, "campaign")


@router.post("/campaigns/{cid}/metrics", response_model=EmailCampaignOut)
def update_campaign_metrics(cid: str, sent: int = 0, opens: int = 0, clicks: int = 0,
                            db: Session = Depends(get_db),
                            user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(EmailCampaign, cid)
    if not obj:
        raise NotFoundError("Campaign not found")
    obj.sent_count += sent
    obj.open_count += opens
    obj.click_count += clicks
    _audit(db, user, "metrics", "campaign", obj.id,
           {"sent": sent, "opens": opens, "clicks": clicks})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/campaigns/{cid}", status_code=204)
def delete_campaign(cid: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(UserRole.admin))):
    _delete(EmailCampaign, db, cid, user, "campaign")
    return None


# ============== Segments =================================================
@router.get("/segments", response_model=list[CustomerSegmentOut])
def list_segments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(CustomerSegment).order_by(CustomerSegment.name)).all()


@router.post("/segments", response_model=CustomerSegmentOut)
def create_segment(payload: CustomerSegmentIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _create(CustomerSegment, db, payload, user, "segment", name_key="name")


@router.patch("/segments/{sid}", response_model=CustomerSegmentOut)
def update_segment(sid: str, payload: CustomerSegmentIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _update(CustomerSegment, db, payload, sid, user, "segment")


@router.delete("/segments/{sid}", status_code=204)
def delete_segment(sid: str, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(UserRole.admin))):
    _delete(CustomerSegment, db, sid, user, "segment")
    return None


@router.get("/segments/{sid}/members", response_model=list[ContactOut])
def segment_members(sid: str, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    seg = db.get(CustomerSegment, sid)
    if not seg:
        raise NotFoundError("Segment not found")
    return crm_svc.evaluate_segment(db, seg)


# ============== Analytics ================================================
@router.get("/analytics", response_model=SalesAnalyticsOut)
def sales_analytics(db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
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
    cursor = today.replace(day=1)
    for _i in range(months_ahead):
        cursor = (cursor + timedelta(days=32)).replace(day=1)
        month_end = (cursor + timedelta(days=32)).replace(day=1)
        deals = db.scalars(
            select(Deal).where(
                Deal.expected_close_date.between(cursor, month_end - timedelta(days=1)),
                ~Deal.stage.in_(("won", "lost")),
            )
        ).all()
        expected = sum((Decimal(d.value) * Decimal(d.probability) / Decimal("100") for d in deals),
                       Decimal("0"))
        months_data.append({
            "period": cursor.strftime("%Y-%m"),
            "expected_revenue": str(expected.quantize(Decimal("0.01"))),
            "deal_count": len(deals),
        })
    return SalesForecastOut(months=months_data, method="probability_weighted")
