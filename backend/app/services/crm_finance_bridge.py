"""CRM ↔ Finance bridge — turn a won deal into a Finance invoice.

This is the keystone integration that makes EnterpriseCore an actual
*suite* rather than two side-by-side silos: closing a CRM deal can now
post a draft invoice into Finance, linking the customer record back to
the original contact.

Design choices
--------------

* **Explicit, not magic.** The conversion is triggered by an endpoint the
  user calls (a "Create invoice" button that appears on won deals), not a
  silent auto-post. Reason: a won deal might already be invoiced, or be
  billed in instalments — silent auto-creation produces duplicate or wrong
  invoices. An optional event subscriber (``auto_invoice_on_won``) is
  provided for teams who *do* want automation, off by default.

* **Find-or-create the customer.** A CRM contact carries a company name +
  email; Finance bills a Customer. We match an existing Customer by email
  (case-insensitive) first, then by exact company name, and only create a
  new one if neither matches — so repeated conversions for the same client
  reuse one customer record instead of spawning duplicates.

* **Idempotent per deal.** Each deal records the id of the invoice it
  generated in its audit trail; calling convert twice returns the existing
  invoice instead of making a second one.

* **Draft status.** The generated invoice lands as ``draft`` so the user
  reviews + sends it deliberately. Nothing is auto-finalised.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm import Contact, Deal
from app.models.finance import Customer, Invoice, InvoiceLine
from app.services import finance as fin


class DealConversionError(Exception):
    """Raised when a deal can't be converted (no contact, zero value, etc.)."""


def _find_or_create_customer(db: Session, contact: Contact | None, deal: Deal) -> Customer:
    """Resolve the Customer to bill for *deal*.

    Match order: contact email → contact company name → deal title fallback.
    Creates a new Customer only when nothing matches.
    """
    email = (contact.email or "").strip().lower() if contact else ""
    company = (contact.company or contact.name or "").strip() if contact else ""

    if email:
        existing = db.scalar(
            select(Customer).where(func.lower(Customer.email) == email)
        )
        if existing:
            return existing
    if company:
        existing = db.scalar(
            select(Customer).where(Customer.name == company)
        )
        if existing:
            return existing

    # Nothing matched — create a fresh customer from the contact.
    name = company or (contact.name if contact else None) or f"Customer for {deal.title}"
    customer = Customer(
        name=name[:180],
        email=(contact.email if contact else None),
        phone=(contact.phone if contact else None),
        currency="USD",
    )
    db.add(customer)
    db.flush()  # assign id without committing the outer tx
    return customer


def find_existing_invoice_for_deal(db: Session, deal_id: str) -> Invoice | None:
    """Return the invoice previously generated from this deal, if any.

    We tag generated invoices with ``notes`` containing a stable marker so
    a second conversion call is idempotent without a schema change.
    """
    marker = _deal_marker(deal_id)
    return db.scalar(
        select(Invoice).where(Invoice.notes.like(f"%{marker}%"))
    )


def _deal_marker(deal_id: str) -> str:
    return f"[from-deal:{deal_id}]"


def convert_deal_to_invoice(
    db: Session,
    deal: Deal,
    *,
    due_in_days: int = 30,
    line_description: str | None = None,
) -> tuple[Invoice, bool]:
    """Create (or return the existing) draft invoice for *deal*.

    Returns ``(invoice, created)`` where ``created`` is False when an invoice
    for this deal already existed.

    Raises :class:`DealConversionError` on un-convertible deals.
    """
    if deal.value is None or Decimal(deal.value) <= 0:
        raise DealConversionError(
            "This deal has no value set, so there's nothing to invoice. "
            "Add a deal value first."
        )

    # Idempotency — one invoice per deal.
    existing = find_existing_invoice_for_deal(db, deal.id)
    if existing is not None:
        return existing, False

    contact = db.get(Contact, deal.contact_id) if deal.contact_id else None
    customer = _find_or_create_customer(db, contact, deal)

    issue = date.today()
    inv = Invoice(
        invoice_number=fin.next_invoice_number(db),
        customer_id=customer.id,
        issue_date=issue,
        due_date=issue + timedelta(days=due_in_days),
        status="draft",
        currency=customer.currency or "USD",
        notes=f"Generated from won deal “{deal.title}”. {_deal_marker(deal.id)}",
    )
    inv.lines.append(
        InvoiceLine(
            description=(line_description or deal.title)[:255],
            quantity=Decimal("1"),
            unit_price=Decimal(deal.value),
            tax_rate=Decimal("0"),
            line_total=Decimal(deal.value),
        )
    )
    fin.recompute_invoice(inv)
    db.add(inv)
    db.flush()
    return inv, True
