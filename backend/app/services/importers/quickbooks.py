"""QuickBooks importer.

Handles two ingest modes from one importer source key:

* CSV (Desktop / Online exports) — Customers, Vendors, Invoices, Expenses.
  Header-only invoice rows are supported in v1; line-item splitting is a
  future enhancement once customers ask for it.
* QuickBooks Online API — when the job's ``config`` carries a ``realm_id``
  plus (``access_token`` or ``refresh_token``) we delegate to
  :mod:`app.services.importers.quickbooks_online`, which pulls data
  directly via Intuit's REST query API.

The dispatcher in ``import_rows`` inspects ``job.config`` to decide which
path to take, so the same importer source key (``"quickbooks"``) covers
both modes.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.import_jobs import ImportJob
from app.services.importers import column_mapping
from app.services.importers.csv_generic import CsvGenericImporter
from app.services.importers import quickbooks_online


QB_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "customer": {
        "name": ["customername", "displayname", "customer"],
        "billing_address": [
            "billingaddressline1", "billaddrline1", "billaddr1",
            "billingaddress", "address",
        ],
        "phone": ["primaryphone", "mobile"],
        "email": ["primaryemail", "email"],
    },
    "vendor": {
        "name": ["vendorname", "displayname", "vendor"],
        "phone": ["primaryphone"],
        "email": ["primaryemail"],
        "payment_terms": ["paymentterms", "terms"],
    },
    "invoice": {
        "invoice_number": ["docnumber", "invoicenumber", "transactionnumber"],
        "issue_date": ["txndate", "transactiondate", "invoicedate", "date"],
        "due_date": ["duedate"],
        "total": ["totalamount", "amount", "total", "balance"],
        "customer_name": ["customer", "customername", "billto"],
    },
    "expense": {
        "date": ["txndate", "expensedate", "date"],
        "amount": ["amount", "totalamount"],
        "vendor_name": ["payee", "vendor"],
        "description": ["memo", "description", "category"],
    },
}


class QuickBooksImporter(CsvGenericImporter):
    source = "quickbooks"
    supported_entities = ["customer", "vendor", "invoice", "expense"]
    description = (
        "QuickBooks Online / Desktop — Customer / Vendor / Invoice / Expense "
        "(CSV export OR QBO REST API)"
    )

    def suggest_mapping(self, source_columns: list[str], target_entity: str) -> dict[str, str]:
        # Both CSV synonym table + the API field-name table are merged so
        # the suggester works in either mode.
        merged = dict(QB_SYNONYMS.get(target_entity, {}))
        for k, v in quickbooks_online.QBO_SYNONYMS.get(target_entity, {}).items():
            merged.setdefault(k, []).extend(v)
        return column_mapping.suggest(source_columns, target_entity, extra_synonyms=merged)

    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        options = dict(job.options or {})
        if job.target_entity in ("customer", "vendor") and "dedup_strategy" not in options:
            options["dedup_strategy"] = "by_name"
            job.options = options
        if job.target_entity == "invoice" and "dedup_strategy" not in options:
            options["dedup_strategy"] = "by_invoice_number"
            job.options = options
        if quickbooks_online.is_api_mode_configured(job.config):
            return quickbooks_online.import_rows_qbo(job, db)
        return super().import_rows(job, db)
