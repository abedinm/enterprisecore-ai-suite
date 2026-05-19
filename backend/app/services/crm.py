"""CRM business logic: proposal/quote PDF, segment evaluation, analytics."""
from __future__ import annotations

import io
import json
from datetime import date
from decimal import Decimal
from secrets import token_hex

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.crm import Contact, CustomerSegment, Deal, Lead, Proposal, Quotation


def generate_quote_number() -> str:
    return f"Q-{date.today().year}-{token_hex(3).upper()}"


def render_proposal_pdf(proposal: Proposal, contact: Contact | None = None,
                        company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Proposal {proposal.title}")
    styles = getSampleStyleSheet()
    story: list = []
    story.append(Paragraph(f"<b>{company_name}</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Proposal:</b> {proposal.title}", styles["BodyText"]))
    story.append(Spacer(1, 4 * mm))

    meta = [
        ["Prepared for:", contact.name if contact else "—"],
        ["Company:", (contact.company if contact else "") or "—"],
        ["Email:", (contact.email if contact else "") or "—"],
        ["Status:", proposal.status.upper()],
        ["Amount:", f"${proposal.amount:.2f}"],
    ]
    t = Table(meta, colWidths=[35 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    if proposal.body:
        for paragraph in proposal.body.split("\n\n"):
            story.append(Paragraph(paragraph.replace("\n", "<br/>"), styles["BodyText"]))
            story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 6 * mm))
    total = Table([["Total proposal value", f"${proposal.amount:.2f}"]],
                  colWidths=[110 * mm, 50 * mm], hAlign="RIGHT")
    total.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(total)
    doc.build(story)
    return buffer.getvalue()


def render_quote_pdf(quote: Quotation, contact: Contact | None = None,
                     company_name: str = "Your Company") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Quote {quote.quote_number}")
    styles = getSampleStyleSheet()
    story: list = []
    story.append(Paragraph(f"<b>{company_name}</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Quote:</b> {quote.quote_number}", styles["BodyText"]))
    story.append(Spacer(1, 4 * mm))

    meta = [
        ["Quoted to:", contact.name if contact else "—"],
        ["Company:", (contact.company if contact else "") or "—"],
        ["Status:", quote.status.upper()],
        ["Quoted total:", f"${quote.total:.2f}"],
    ]
    t = Table(meta, colWidths=[35 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    total = Table([["Total quoted", f"${quote.total:.2f}"]],
                  colWidths=[110 * mm, 50 * mm], hAlign="RIGHT")
    total.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10b981")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(total)
    doc.build(story)
    return buffer.getvalue()


def evaluate_segment(db: Session, segment: CustomerSegment) -> list[Contact]:
    """Evaluate segment rules to return matching contacts.

    Rules JSON shape:
        {
          "company_like": "Acme",
          "email_domain": "example.com",
          "tag": "vip",
          "has_open_deals": true
        }
    All conditions are AND-combined.
    """
    try:
        rules = json.loads(segment.rules or "{}")
    except Exception:
        rules = {}

    stmt = select(Contact)
    if rules.get("company_like"):
        stmt = stmt.where(Contact.company.ilike(f"%{rules['company_like']}%"))
    if rules.get("email_domain"):
        stmt = stmt.where(Contact.email.ilike(f"%@{rules['email_domain']}"))
    if rules.get("tag"):
        stmt = stmt.where(Contact.tags.ilike(f"%{rules['tag']}%"))
    contacts = db.scalars(stmt).all()
    if rules.get("has_open_deals"):
        open_contact_ids = {d.contact_id for d in db.scalars(
            select(Deal).where(~Deal.stage.in_(("won", "lost")))
        ).all() if d.contact_id}
        contacts = [c for c in contacts if c.id in open_contact_ids]
    return contacts
