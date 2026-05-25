"""Salesforce importer.

Handles both:

* CSV exports — Data Loader / Reports for Contacts, Accounts,
  Opportunities. Same flow as every other CSV importer.
* REST API mode — when the job's ``config`` carries ``instance_url`` +
  (``access_token`` or ``refresh_token``) we delegate import / suggest
  to :mod:`app.services.importers.salesforce_rest`, which pulls data
  directly via the SOQL query endpoint.

Mode selection is per-job: the dispatcher in ``import_rows`` inspects
``job.config`` and routes accordingly, so the same importer source key
(``"salesforce"``) covers both paths and there's no separate REST source
to register in the importer registry.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.import_jobs import ImportJob
from app.services.importers import column_mapping
from app.services.importers.csv_generic import CsvGenericImporter
from app.services.importers import salesforce_rest


SF_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "contact": {
        "first_name": ["firstname"],
        "last_name": ["lastname"],
        "email": ["email"],
        "phone": ["phone", "mobilephone"],
        "company": ["accountname", "account"],
    },
    "customer": {
        "name": ["accountname", "name"],
        "phone": ["phone"],
        "billing_address": ["billingstreet", "billingaddress"],
    },
    "deal": {
        "title": ["name", "opportunityname"],
        "value": ["amount"],
        "stage": ["stagename", "stage"],
        "expected_close_date": ["closedate"],
        "probability": ["probability"],
    },
}


class SalesforceImporter(CsvGenericImporter):
    source = "salesforce"
    supported_entities = ["contact", "customer", "deal"]
    description = "Salesforce CRM (Contact / Account / Opportunity — CSV export OR REST API)"

    # ---- Mapping ----------------------------------------------------------
    def suggest_mapping(self, source_columns: list[str], target_entity: str) -> dict[str, str]:
        # Same heuristic for both modes — synonym table covers REST field names
        # (FirstName, Email, Account.Name → account_name) and CSV column names.
        merged = dict(SF_SYNONYMS.get(target_entity, {}))
        for k, v in salesforce_rest.SF_REST_SYNONYMS.get(target_entity, {}).items():
            merged.setdefault(k, []).extend(v)
        return column_mapping.suggest(source_columns, target_entity, extra_synonyms=merged)

    # ---- Commit dispatch ---------------------------------------------------
    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        options = dict(job.options or {})
        if job.target_entity == "contact" and "dedup_strategy" not in options:
            options["dedup_strategy"] = "by_email"
            job.options = options
        if salesforce_rest.is_rest_mode_configured(job.config):
            return salesforce_rest.import_rows_rest(job, db)
        return super().import_rows(job, db)
