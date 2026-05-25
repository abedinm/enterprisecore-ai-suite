"""Importer registry — single place that maps ``source`` → concrete class.

The dict is the source of truth used by both the API discovery endpoint
(``GET /api/v1/importers``) and the upload endpoint (which resolves an
incoming ``source`` form field to an importer).

To add a new importer:
    1. write a subclass of :class:`Importer` in its own module
    2. import it here
    3. add an entry to :data:`IMPORTERS`
The endpoint surface picks up the new source automatically.
"""
from __future__ import annotations

from app.services.importers.asana import AsanaImporter
from app.services.importers.base import Importer
from app.services.importers.csv_generic import CsvGenericImporter
from app.services.importers.hubspot import HubSpotImporter
from app.services.importers.microsoft_project import MicrosoftProjectImporter
from app.services.importers.notion import NotionImporter
from app.services.importers.quickbooks import QuickBooksImporter
from app.services.importers.salesforce import SalesforceImporter
from app.services.importers.trello import TrelloImporter


IMPORTERS: dict[str, type[Importer]] = {
    # CRM / finance / HR
    "hubspot": HubSpotImporter,
    "salesforce": SalesforceImporter,
    "quickbooks": QuickBooksImporter,
    "csv": CsvGenericImporter,
    # Project management
    "asana": AsanaImporter,
    "notion": NotionImporter,
    "trello": TrelloImporter,
    "microsoft_project": MicrosoftProjectImporter,
}


def get_importer(source: str) -> Importer:
    """Resolve a source string to a freshly-built importer instance."""
    cls = IMPORTERS.get(source)
    if not cls:
        raise ValueError(f"Unknown importer source '{source}'")
    return cls()
