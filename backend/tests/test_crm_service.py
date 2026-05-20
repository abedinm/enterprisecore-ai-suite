"""Service-level CRM tests — covers proposal/quote PDF generation and segment
evaluation logic that the HTTP-level CRM suite doesn't exercise directly.

Target: raise app/services/crm.py coverage from 24% toward 80%+.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.crm import Contact, CustomerSegment, Deal, Proposal, Quotation
from app.services import crm


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def crm_contacts(session_factory):
    """Seed four contacts with distinct company/email/tag combinations."""
    import uuid
    sfx = uuid.uuid4().hex[:8]
    with session_factory() as db:
        contacts = [
            Contact(name=f"Alice_{sfx}",  company=f"Acme_{sfx}",    email=f"alice-{sfx}@acme.io",    tags='["vip","gold"]'),
            Contact(name=f"Bob_{sfx}",    company=f"Globex_{sfx}",  email=f"bob-{sfx}@globex.io",    tags='["silver"]'),
            Contact(name=f"Carol_{sfx}",  company=f"Acme_{sfx}",    email=f"carol-{sfx}@acme.io",    tags='["vip"]'),
            Contact(name=f"Dave_{sfx}",   company=f"Initech_{sfx}", email=f"dave-{sfx}@initech.io",  tags='[]'),
        ]
        for c in contacts:
            db.add(c)
        db.flush()
        ids = [c.id for c in contacts]
        # Alice has an open deal; Dave has a won (closed) deal; Bob/Carol have none
        db.add(Deal(contact_id=ids[0], title=f"Deal_A_{sfx}", stage="proposal",
                    value=Decimal("5000"), probability=Decimal("60")))
        db.add(Deal(contact_id=ids[3], title=f"Deal_D_{sfx}", stage="won",
                    value=Decimal("3000"), probability=Decimal("100")))
        db.commit()
        yield {"alice": ids[0], "bob": ids[1], "carol": ids[2], "dave": ids[3],
               "sfx": sfx}


def _make_segment(db, name: str, rules: dict) -> CustomerSegment:
    seg = CustomerSegment(name=name, rules=json.dumps(rules))
    db.add(seg)
    db.flush()
    return seg


def _make_proposal(amount: Decimal = Decimal("9500"), body: str = "") -> Proposal:
    return Proposal(title="Enterprise Widget Deal", status="sent", amount=amount, body=body)


def _make_quotation(total: Decimal = Decimal("4200")) -> Quotation:
    return Quotation(quote_number=crm.generate_quote_number(), status="draft", total=total)


# ---------------------------------------------------------------------------
# generate_quote_number
# ---------------------------------------------------------------------------

def test_generate_quote_number_format():
    qn = crm.generate_quote_number()
    # Expected pattern: "Q-<year>-<6 hex chars uppercase>"
    year = str(date.today().year)
    assert qn.startswith(f"Q-{year}-"), f"unexpected format: {qn}"
    suffix = qn.split("-", 2)[2]
    assert len(suffix) == 6
    assert suffix == suffix.upper()
    assert all(c in "0123456789ABCDEF" for c in suffix)


def test_generate_quote_number_unique():
    """Two successive calls must not produce the same token."""
    a = crm.generate_quote_number()
    b = crm.generate_quote_number()
    assert a != b


# ---------------------------------------------------------------------------
# render_proposal_pdf
# ---------------------------------------------------------------------------

def test_render_proposal_pdf_returns_pdf_bytes():
    prop = _make_proposal()
    pdf = crm.render_proposal_pdf(prop)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 0
    assert pdf[:4] == b"%PDF"


def test_render_proposal_pdf_no_contact():
    """contact=None should fill all fields with em-dashes and not crash."""
    prop = _make_proposal()
    pdf = crm.render_proposal_pdf(prop, contact=None, company_name="TestCo")
    assert pdf[:4] == b"%PDF"


def test_render_proposal_pdf_with_contact():
    contact = Contact(name="Eve", company="Umbrella", email="eve@umbrella.corp")
    prop = _make_proposal(amount=Decimal("12345.67"), body="Dear Eve,\n\nWe are pleased to offer...")
    pdf = crm.render_proposal_pdf(prop, contact=contact, company_name="Widgets Inc.")
    assert pdf[:4] == b"%PDF"


def test_render_proposal_pdf_multiline_body():
    """Multi-paragraph body splits on double newline — should not crash."""
    body = "Paragraph one.\n\nParagraph two.\n\nParagraph three with $pecial chars & <html> = &amp;."
    prop = _make_proposal(body=body)
    pdf = crm.render_proposal_pdf(prop, company_name="WidgetCo")
    assert pdf[:4] == b"%PDF"


def test_render_proposal_pdf_zero_amount():
    prop = _make_proposal(amount=Decimal("0.00"))
    pdf = crm.render_proposal_pdf(prop)
    assert pdf[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# render_quote_pdf
# ---------------------------------------------------------------------------

def test_render_quote_pdf_returns_pdf_bytes():
    quote = _make_quotation()
    pdf = crm.render_quote_pdf(quote)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_render_quote_pdf_no_contact():
    quote = _make_quotation()
    pdf = crm.render_quote_pdf(quote, contact=None, company_name="TestCo")
    assert pdf[:4] == b"%PDF"


def test_render_quote_pdf_with_contact():
    contact = Contact(name="Frank", company="Acme", email="frank@acme.io")
    quote = _make_quotation(total=Decimal("99999.99"))
    pdf = crm.render_quote_pdf(quote, contact=contact, company_name="Widget Global")
    assert pdf[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# evaluate_segment
# ---------------------------------------------------------------------------

def test_evaluate_segment_empty_rules_returns_all(session_factory, crm_contacts):
    """No rules → all contacts are returned."""
    sfx = crm_contacts["sfx"]
    with session_factory() as db:
        seg = _make_segment(db, f"All_{sfx}", {})
        results = crm.evaluate_segment(db, seg)
    assert len(results) >= 4  # at least the four we seeded


def test_evaluate_segment_company_like(session_factory, crm_contacts):
    """company_like filters contacts whose company contains the substring."""
    sfx = crm_contacts["sfx"]
    with session_factory() as db:
        seg = _make_segment(db, f"AcmeSeg_{sfx}", {"company_like": f"Acme_{sfx}"})
        results = crm.evaluate_segment(db, seg)
    ids = {c.id for c in results}
    # Alice and Carol belong to Acme; Bob and Dave don't
    assert crm_contacts["alice"] in ids
    assert crm_contacts["carol"] in ids
    assert crm_contacts["bob"] not in ids
    assert crm_contacts["dave"] not in ids


def test_evaluate_segment_email_domain(session_factory, crm_contacts):
    """email_domain filters contacts whose email ends with @<domain>."""
    sfx = crm_contacts["sfx"]
    with session_factory() as db:
        seg = _make_segment(db, f"GlobexSeg_{sfx}", {"email_domain": f"globex.io"})
        results = crm.evaluate_segment(db, seg)
    ids = {c.id for c in results}
    # Bob's email ends with @globex.io (includes the sfx prefix so it still matches)
    assert crm_contacts["bob"] in ids
    assert crm_contacts["alice"] not in ids


def test_evaluate_segment_tag(session_factory, crm_contacts):
    """tag filters contacts whose tags JSON string contains the value."""
    sfx = crm_contacts["sfx"]
    with session_factory() as db:
        seg = _make_segment(db, f"VipSeg_{sfx}", {"tag": "vip"})
        results = crm.evaluate_segment(db, seg)
    ids = {c.id for c in results}
    assert crm_contacts["alice"] in ids  # has ["vip","gold"]
    assert crm_contacts["carol"] in ids  # has ["vip"]
    assert crm_contacts["bob"] not in ids   # only ["silver"]
    assert crm_contacts["dave"] not in ids  # empty tags


def test_evaluate_segment_has_open_deals(session_factory, crm_contacts):
    """has_open_deals:true retains only contacts that have a non-won/lost deal."""
    sfx = crm_contacts["sfx"]
    with session_factory() as db:
        seg = _make_segment(db, f"OpenDealSeg_{sfx}", {"has_open_deals": True})
        results = crm.evaluate_segment(db, seg)
    ids = {c.id for c in results}
    # Alice has stage="proposal" (open); Dave has stage="won" (closed); Bob/Carol have none
    assert crm_contacts["alice"] in ids
    assert crm_contacts["dave"] not in ids   # won is closed
    assert crm_contacts["bob"] not in ids    # no deal
    assert crm_contacts["carol"] not in ids  # no deal


def test_evaluate_segment_combined_and(session_factory, crm_contacts):
    """Multiple rules are AND-combined: only contacts matching ALL conditions."""
    sfx = crm_contacts["sfx"]
    with session_factory() as db:
        # Must be in Acme AND have tag "vip"
        seg = _make_segment(db, f"AcmeVip_{sfx}",
                            {"company_like": f"Acme_{sfx}", "tag": "vip"})
        results = crm.evaluate_segment(db, seg)
    ids = {c.id for c in results}
    # Alice: Acme ✓ + vip ✓ → in
    # Carol: Acme ✓ + vip ✓ → in
    # Bob:   Globex ✗ → out (even though silver tag matches tag≠vip)
    # Dave:  Initech ✗ → out
    assert crm_contacts["alice"] in ids
    assert crm_contacts["carol"] in ids
    assert crm_contacts["bob"] not in ids
    assert crm_contacts["dave"] not in ids


def test_evaluate_segment_invalid_json_rules(session_factory):
    """Malformed rules JSON must not raise — should be treated as {}."""
    import uuid
    sfx = uuid.uuid4().hex[:8]
    with session_factory() as db:
        seg = CustomerSegment(name=f"BadJSON_{sfx}", rules="<<<not json>>>")
        db.add(seg)
        db.flush()
        results = crm.evaluate_segment(db, seg)
    # Should return all contacts (no filters applied), not raise
    assert isinstance(results, list)


def test_evaluate_segment_no_match(session_factory):
    """A very specific company_like that matches nothing returns empty list."""
    import uuid
    sfx = uuid.uuid4().hex[:8]
    with session_factory() as db:
        seg = _make_segment(db, f"NoMatch_{sfx}",
                            {"company_like": f"DefinitelyNoSuchCompany_{sfx}"})
        results = crm.evaluate_segment(db, seg)
    assert results == []
