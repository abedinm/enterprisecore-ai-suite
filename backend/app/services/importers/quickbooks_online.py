"""QuickBooks Online (QBO) API importer mode.

QBO uses Intuit's OAuth2 + REST API. The customer has to register a
Connected App in https://developer.intuit.com (out of our scope), then
supply us with three things:

* ``realm_id`` — the QBO company id (Intuit calls it "company id" in
  the docs; the OAuth grant calls it ``realmId``)
* ``refresh_token`` — the long-lived OAuth grant
* (server) ``INTUIT_CLIENT_ID`` + ``INTUIT_CLIENT_SECRET`` env

The refresh-token grant exchanges those for a short-lived access_token
(1 hour) at https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer.

Sandbox vs production
=====================
The host is different between sandbox + production:

* sandbox    → https://sandbox-quickbooks.api.intuit.com
* production → https://quickbooks.api.intuit.com

Set ``sandbox: true`` in the job config to use the sandbox host.

Entities
========
Customer, Vendor, Invoice, Expense. Each maps to a corresponding QBO
table queried via the QBO query API:

    GET <base>/v3/company/<realmId>/query?query=SELECT * FROM Customer
"""
from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Any, Iterable, Iterator

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, ValidationFailed
from app.models.import_jobs import ImportJob
from app.services.importers import column_mapping
from app.services.importers.base import _apply_mapping
from app.services.importers.csv_generic import ENTITY_TARGETS, _coerce


PRODUCTION_BASE = "https://quickbooks.api.intuit.com"
SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
DEFAULT_MINOR_VERSION = "65"
DEFAULT_MAX_RECORDS = 100_000
PAGE_SIZE = 500  # QBO maximum allowed in one query response


# Entity -> QBO table name in the SELECT.
QBO_TABLE_BY_ENTITY: dict[str, str] = {
    "customer": "Customer",
    "vendor": "Vendor",
    "invoice": "Invoice",
    "expense": "Purchase",
}


# QBO returns nested CamelCase JSON. We flatten + lowercase so the
# column_mapping suggester can match against canonical names.
# Source columns are the keys our ``_flatten_record`` actually produces
# from a QBO API response. The first entry per EC field is the primary
# choice — the column_mapping suggester walks the source columns in the
# order ``detect_columns`` returns them, so primary entries come first
# in that list too.
QBO_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "customer": {
        "name": ["displayname", "fullyqualifiedname"],
        "email": ["primaryemailaddr_address"],
        "phone": ["primaryphone_freeformnumber"],
        "billing_address": ["billaddr_line1"],
    },
    "vendor": {
        "name": ["displayname", "fullyqualifiedname"],
        "email": ["primaryemailaddr_address"],
        "phone": ["primaryphone_freeformnumber"],
    },
    "invoice": {
        "invoice_number": ["docnumber"],
        "issue_date": ["txndate"],
        "due_date": ["duedate"],
        "total": ["totalamt", "balance"],
        "customer_name": ["customerref_name"],
    },
    "expense": {
        "date": ["txndate"],
        "amount": ["totalamt"],
        "vendor_name": ["entityref_name", "accountref_name"],
        "description": ["privatenote", "memo"],
    },
}


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
def mint_access_token(
    refresh_token: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout: float = 15.0,
) -> str:
    """Exchange a QBO refresh_token for a short-lived access_token."""
    client_id = client_id or os.environ.get("INTUIT_CLIENT_ID", "")
    client_secret = client_secret or os.environ.get("INTUIT_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        raise ValidationFailed(
            "INTUIT_CLIENT_ID / INTUIT_CLIENT_SECRET must be configured "
            "to refresh QuickBooks credentials"
        )
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {basic}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    resp = httpx.post(TOKEN_URL, data=body, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise AuthenticationError("Refresh QuickBooks credentials")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise AuthenticationError("Refresh QuickBooks credentials")
    return token


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------
class QboClient:
    """Minimal Intuit QBO REST client — query API + pagination."""

    def __init__(
        self,
        realm_id: str,
        access_token: str,
        *,
        sandbox: bool = False,
        minor_version: str = DEFAULT_MINOR_VERSION,
        timeout: float = 30.0,
    ):
        self.realm_id = realm_id
        self.access_token = access_token
        self.base_url = SANDBOX_BASE if sandbox else PRODUCTION_BASE
        self.minor_version = minor_version
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def query(self, table: str, *, max_records: int = DEFAULT_MAX_RECORDS) -> Iterator[dict[str, Any]]:
        """Stream every record from a QBO table via the query API.

        QBO pagination uses STARTPOSITION / MAXRESULTS — not cursor URLs.
        We page in ``PAGE_SIZE`` chunks until the response is short.
        """
        start = 1
        yielded = 0
        while True:
            soql = f"SELECT * FROM {table} STARTPOSITION {start} MAXRESULTS {PAGE_SIZE}"
            url = f"{self.base_url}/v3/company/{self.realm_id}/query"
            params = {"query": soql, "minorversion": self.minor_version}
            resp = httpx.get(url, params=params, headers=self._headers, timeout=self.timeout)
            if resp.status_code == 401:
                raise AuthenticationError("Refresh QuickBooks credentials")
            if resp.status_code >= 400:
                raise ValidationFailed(
                    f"QBO query failed ({resp.status_code}): {resp.text[:200]}"
                )
            data = resp.json()
            query_resp = data.get("QueryResponse") or {}
            records = query_resp.get(table) or []
            if not records:
                return
            for record in records:
                yield record
                yielded += 1
                if yielded >= max_records:
                    return
            if len(records) < PAGE_SIZE:
                return
            start += PAGE_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _flatten_record(rec: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
    """Recursively flatten a nested QBO record.

    Keys are joined with ``_`` and lowercased so suggest() can match.
    Lists are skipped (QBO returns line items as lists; we only want the
    header-level fields for the v1 importer — line splitting can come
    later).
    """
    flat: dict[str, Any] = {}
    for key, value in rec.items():
        new_key = f"{parent_key}_{key}".strip("_").lower() if parent_key else key.lower()
        if isinstance(value, dict):
            flat.update(_flatten_record(value, new_key))
        elif isinstance(value, list):
            continue
        else:
            flat[new_key] = value
    return flat


def suggest_mapping_qbo(source_columns: list[str], target_entity: str) -> dict[str, str]:
    return column_mapping.suggest(
        source_columns,
        target_entity,
        extra_synonyms=QBO_SYNONYMS.get(target_entity, {}),
    )


def _build_client_from_config(config: dict[str, Any]) -> QboClient:
    realm_id = config.get("realm_id") or ""
    if not realm_id:
        raise ValidationFailed("QuickBooks Online mode requires a realm_id")
    access_token = config.get("access_token") or ""
    refresh_token = config.get("refresh_token") or ""
    if not access_token:
        if not refresh_token:
            raise AuthenticationError("Refresh QuickBooks credentials")
        access_token = mint_access_token(
            refresh_token,
            client_id=config.get("client_id"),
            client_secret=config.get("client_secret"),
        )
    return QboClient(realm_id, access_token, sandbox=bool(config.get("sandbox", False)))


def fetch_records(
    target_entity: str,
    config: dict[str, Any],
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> Iterable[dict[str, Any]]:
    table = QBO_TABLE_BY_ENTITY.get(target_entity)
    if not table:
        raise ValidationFailed(
            f"QuickBooks Online mode does not support entity '{target_entity}'"
        )
    client = _build_client_from_config(config)
    for raw in client.query(table, max_records=max_records):
        yield _flatten_record(raw)


def is_api_mode_configured(job_config: dict[str, Any] | None) -> bool:
    if not job_config:
        return False
    if not job_config.get("realm_id"):
        return False
    return bool(job_config.get("access_token") or job_config.get("refresh_token"))


def detect_columns(target_entity: str) -> list[str]:
    """A best-effort guess at what the QBO API returns for the entity.

    Used by suggest-mapping before any data has been fetched. Order is
    significant — the column_mapping suggester picks the first matching
    source column per EC field, so the primary column for each EC field
    has to come first. Anything we miss here is still reachable through
    the manual mapping PATCH endpoint.
    """
    synonyms = QBO_SYNONYMS.get(target_entity, {})
    cols: list[str] = []
    seen: set[str] = set()
    for choices in synonyms.values():
        for c in choices:
            if c not in seen:
                cols.append(c)
                seen.add(c)
    return cols


# ---------------------------------------------------------------------------
# Commit path
# ---------------------------------------------------------------------------
def import_rows_qbo(job: ImportJob, db: Session, *, max_records: int = DEFAULT_MAX_RECORDS) -> ImportJob:
    target = ENTITY_TARGETS.get(job.target_entity)
    if not target:
        job.status = "failed"
        return job
    model = target["model"]
    entity_key = target["entity_key"]
    required = target["required"]
    options = job.options or {}
    on_conflict = options.get("on_conflict", "skip")
    dedup_strategy = options.get("dedup_strategy")

    mapping = job.column_mapping or {}
    row_no = 0
    imported = skipped = failed = 0
    imported_ids: list[list[str]] = list(job.imported_record_ids or [])
    seen_dedup_keys: set[str] = set()

    config = dict(job.config or {})

    try:
        for raw in fetch_records(job.target_entity, config, max_records=max_records):
            row_no += 1
            try:
                mapped = _apply_mapping(raw, mapping)
                typed = {k: _coerce(k, v) for k, v in mapped.items()}
                typed = {k: v for k, v in typed.items() if v is not None}

                missing = [f for f in required if not typed.get(f)]
                if missing:
                    failed += 1
                    continue

                if dedup_strategy:
                    key = _dedup_key(typed, dedup_strategy)
                    if key:
                        if key in seen_dedup_keys:
                            skipped += 1
                            continue
                        seen_dedup_keys.add(key)

                existing = _find_existing(db, model, typed, dedup_strategy) if dedup_strategy else None
                if existing is not None:
                    if on_conflict == "skip":
                        skipped += 1
                        continue
                    if on_conflict == "update":
                        for k, v in typed.items():
                            if hasattr(existing, k):
                                setattr(existing, k, v)
                        db.flush()
                        imported += 1
                        imported_ids.append([entity_key, existing.id])
                        continue

                valid_attrs = {k: v for k, v in typed.items() if hasattr(model, k)}
                obj = model(**valid_attrs)
                db.add(obj)
                db.flush()
                imported += 1
                imported_ids.append([entity_key, obj.id])
            except Exception:  # pragma: no cover - defensive
                failed += 1
    except AuthenticationError:
        job.status = "failed"
        db.flush()
        raise

    job.row_count_total = row_no
    job.row_count_imported = imported
    job.row_count_skipped = skipped
    job.row_count_failed = failed
    job.imported_record_ids = imported_ids
    job.status = "completed"
    job.completed_at = datetime.now()
    db.flush()
    return job


def _dedup_key(mapped: dict[str, Any], strategy: str) -> str | None:
    if strategy == "by_name":
        return (mapped.get("name") or "").lower() or None
    if strategy == "by_invoice_number":
        return mapped.get("invoice_number") or None
    if strategy == "by_email":
        return (mapped.get("email") or "").lower() or None
    return None


def _find_existing(db: Session, model, mapped: dict[str, Any], strategy: str):
    from sqlalchemy import select

    if strategy == "by_name" and mapped.get("name"):
        return db.scalar(select(model).where(model.name == mapped["name"]))
    if strategy == "by_invoice_number" and mapped.get("invoice_number"):
        return db.scalar(select(model).where(model.invoice_number == mapped["invoice_number"]))
    if strategy == "by_email" and mapped.get("email"):
        return db.scalar(select(model).where(model.email == mapped["email"]))
    return None
