"""Data-migration importers.

The registry that maps ``source`` → concrete :class:`Importer` lives in
:mod:`app.services.importers.registry`. This package re-exports the
high-traffic symbols (``IMPORTERS`` and ``get_importer``) so existing
callers ``from app.services.importers import IMPORTERS`` keep working.
"""
from __future__ import annotations

from app.services.importers.asana import AsanaImporter
from app.services.importers.base import Importer
from app.services.importers.csv_generic import CsvGenericImporter
from app.services.importers.hubspot import HubSpotImporter
from app.services.importers.microsoft_project import MicrosoftProjectImporter
from app.services.importers.notion import NotionImporter
from app.services.importers.quickbooks import QuickBooksImporter
from app.services.importers.registry import IMPORTERS, get_importer
from app.services.importers.salesforce import SalesforceImporter
from app.services.importers.trello import TrelloImporter


__all__ = [
    "Importer",
    "CsvGenericImporter",
    "HubSpotImporter",
    "QuickBooksImporter",
    "SalesforceImporter",
    "AsanaImporter",
    "NotionImporter",
    "TrelloImporter",
    "MicrosoftProjectImporter",
    "IMPORTERS",
    "get_importer",
]
