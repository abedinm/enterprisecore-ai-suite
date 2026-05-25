"""HubSpot CSV importer.

Drop-in handler for the CSV exports produced by Settings → Export →
Contacts / Companies / Deals in HubSpot CRM. Adds HubSpot-specific
column synonyms on top of the generic suggester and delegates the actual
INSERT machinery to :class:`CsvGenericImporter`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.import_jobs import ImportJob
from app.services.importers import column_mapping
from app.services.importers.csv_generic import CsvGenericImporter


HUBSPOT_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "contact": {
        "name": ["fullname"],
        "first_name": ["firstname"],
        "last_name": ["lastname"],
        "email": ["email"],
        "phone": ["phonenumber"],
        "company": ["company", "associatedcompany"],
    },
    "customer": {
        "name": ["companyname", "company"],
        "billing_address": ["streetaddress", "address"],
        "phone": ["phonenumber"],
    },
    "deal": {
        "title": ["dealname"],
        "value": ["amount"],
        "stage": ["dealstage", "stage"],
        "expected_close_date": ["closedate"],
    },
}


class HubSpotImporter(CsvGenericImporter):
    source = "hubspot"
    supported_entities = ["contact", "customer", "deal"]
    description = "HubSpot CRM (Contacts / Companies / Deals CSV exports)"

    def suggest_mapping(self, source_columns: list[str], target_entity: str) -> dict[str, str]:
        return column_mapping.suggest(
            source_columns,
            target_entity,
            extra_synonyms=HUBSPOT_SYNONYMS.get(target_entity, {}),
        )

    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        # Default dedup strategy for HubSpot contacts is by email — overrideable.
        options = dict(job.options or {})
        if job.target_entity == "contact" and "dedup_strategy" not in options:
            options["dedup_strategy"] = "by_email"
            job.options = options
        return super().import_rows(job, db)
