"""Heuristics for auto-detecting source columns → EnterpriseCore fields.

Each target entity has a list of candidate EC field names and, for each,
a list of source-column synonyms we recognize. Synonyms are matched
case-insensitively after stripping whitespace + punctuation, so
``"E-mail address"`` finds ``"email"``.
"""
from __future__ import annotations

import re


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# entity -> {ec_field: [source synonym ...]}
SYNONYMS: dict[str, dict[str, list[str]]] = {
    "contact": {
        "name": ["name", "fullname", "contactname", "displayname"],
        "first_name": ["firstname", "givenname", "first"],
        "last_name": ["lastname", "surname", "familyname", "last"],
        "email": ["email", "emailaddress", "primaryemail", "workemail", "mail"],
        "phone": ["phone", "phonenumber", "mobile", "mobilephone", "tel", "telephone"],
        "company": ["company", "companyname", "organization", "account", "accountname", "employer"],
    },
    "customer": {
        "name": ["customername", "name", "company", "companyname", "displayname"],
        "email": ["email", "primaryemail", "emailaddress", "billingemail"],
        "phone": ["phone", "phonenumber", "primaryphone", "mobile"],
        "billing_address": [
            "billingaddress", "billingaddressline1", "address", "addressline1",
            "shippingaddress", "billingstreet",
        ],
        "currency": ["currency", "currencycode"],
    },
    "vendor": {
        "name": ["vendorname", "name", "company", "supplier", "suppliername"],
        "email": ["email", "primaryemail", "emailaddress"],
        "phone": ["phone", "phonenumber", "mobile"],
        "payment_terms": ["paymentterms", "terms"],
    },
    "deal": {
        "title": ["dealname", "name", "opportunityname", "deal", "title"],
        "value": ["amount", "value", "dealamount", "opportunityamount"],
        "stage": ["stage", "stagename", "dealstage", "pipelinestage"],
        "expected_close_date": ["closedate", "expectedclose", "expectedclosedate", "closingdate"],
        "probability": ["probability", "winprobability"],
    },
    "invoice": {
        "invoice_number": ["invoicenumber", "invoiceno", "invoice", "docnumber", "number"],
        "customer_name": ["customer", "customername", "billto", "client"],
        "issue_date": ["invoicedate", "issuedate", "date"],
        "due_date": ["duedate", "due"],
        "total": ["total", "totalamount", "amount", "balance"],
        "currency": ["currency", "currencycode"],
    },
    "expense": {
        "date": ["date", "transactiondate", "expensedate", "postdate"],
        "amount": ["amount", "total", "expenseamount"],
        "vendor_name": ["vendor", "vendorname", "payee", "supplier"],
        "description": ["description", "memo", "notes", "category"],
        "currency": ["currency", "currencycode"],
    },
    "employee": {
        "full_name": ["name", "fullname", "employeename"],
        "employee_code": ["employeeid", "employeenumber", "code", "empid"],
        "email": ["email", "workemail", "emailaddress"],
        "department": ["department", "dept"],
        "title": ["title", "jobtitle", "position"],
        "hire_date": ["hiredate", "startdate", "joindate"],
    },
}


def suggest(
    source_columns: list[str],
    target_entity: str,
    extra_synonyms: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Return ``{source_col: ec_field}`` for the best guesses.

    Pass ``extra_synonyms`` to extend the built-in dictionary for
    source-specific column names (e.g. HubSpot's "Lifecycle Stage").
    """
    if target_entity not in SYNONYMS:
        return {}
    table = dict(SYNONYMS[target_entity])
    if extra_synonyms:
        for ec_field, syns in extra_synonyms.items():
            table.setdefault(ec_field, []).extend(syns)

    # Pre-normalize the lookup
    normalized_table = {
        ec_field: {_normalize(s) for s in syns} for ec_field, syns in table.items()
    }

    out: dict[str, str] = {}
    used_ec_fields: set[str] = set()
    for src in source_columns:
        norm = _normalize(src)
        best_field: str | None = None
        for ec_field, syns in normalized_table.items():
            if ec_field in used_ec_fields and ec_field not in ("first_name", "last_name"):
                # Allow first_name + last_name both to fire on a single composite
                continue
            if norm in syns:
                best_field = ec_field
                break
        if not best_field:
            # Fallback: substring match in either direction
            for ec_field, syns in normalized_table.items():
                if ec_field in used_ec_fields:
                    continue
                if any(norm and (norm in s or s in norm) for s in syns):
                    best_field = ec_field
                    break
        if best_field:
            out[src] = best_field
            used_ec_fields.add(best_field)
    return out


def target_fields_for(target_entity: str) -> list[str]:
    """Return the canonical EC field names known for ``target_entity``."""
    return list(SYNONYMS.get(target_entity, {}).keys())
