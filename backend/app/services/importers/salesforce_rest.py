"""Salesforce REST API importer mode.

Pulls Contacts / Accounts / Opportunities directly from a customer's
Salesforce org over the REST API, bypassing the CSV export step entirely.
The CSV importer (`salesforce.py`) keeps its responsibilities — this
module owns the API path and is auto-selected by the dispatcher in
`salesforce.py` when the job carries REST credentials in its config.

Auth flow
=========
The customer registers a Connected App in their Salesforce setup, sets
``SALESFORCE_CLIENT_ID`` + ``SALESFORCE_CLIENT_SECRET`` on the server,
and supplies their own ``refresh_token`` (one-time interactive consent).
We mint short-lived access tokens via the OAuth refresh-token grant:

    POST <instance_url>/services/oauth2/token
        grant_type=refresh_token
        client_id=<CLIENT_ID>
        client_secret=<CLIENT_SECRET>
        refresh_token=<token>

If the customer supplies a long-lived access_token directly we skip the
refresh dance and use it as-is.

Scopes used
===========
The connected app needs at minimum ``api`` + ``refresh_token`` /
``offline_access``. Read-only queries don't require ``full``.

Pagination
==========
The query endpoint returns one page of records and a ``nextRecordsUrl``
when more remain. We follow that link until ``done`` is true OR the
configured row cap (default 100k) is reached.
"""
from __future__ import annotations

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


DEFAULT_API_VERSION = "v60.0"
DEFAULT_MAX_RECORDS = 100_000

# Entity -> SOQL SELECT statement we issue. Fields are chosen to line up
# with the EC target schema's required + commonly-used columns.
SOQL_BY_ENTITY: dict[str, str] = {
    "contact": (
        "SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, "
        "AccountId, Account.Name FROM Contact"
    ),
    "customer": "SELECT Id, Name, Phone, BillingStreet, BillingCity FROM Account",
    "deal": (
        "SELECT Id, Name, Amount, StageName, CloseDate, Probability, "
        "AccountId FROM Opportunity"
    ),
}


# Same synonym shape the CSV importer uses — the field names on the right
# are what SOQL returns (``FirstName``, ``LastName``, etc), normalised
# through the same suggest() heuristic.
SF_REST_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "contact": {
        "first_name": ["firstname"],
        "last_name": ["lastname"],
        "email": ["email"],
        "phone": ["phone", "mobilephone"],
        "company": ["account_name", "accountname"],
    },
    "customer": {
        "name": ["name"],
        "phone": ["phone"],
        "billing_address": ["billingstreet"],
    },
    "deal": {
        "title": ["name"],
        "value": ["amount"],
        "stage": ["stagename"],
        "expected_close_date": ["closedate"],
        "probability": ["probability"],
    },
}


# ---------------------------------------------------------------------------
# OAuth helper
# ---------------------------------------------------------------------------
def mint_access_token(
    instance_url: str,
    refresh_token: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout: float = 15.0,
) -> str:
    """Exchange a refresh_token for a short-lived access_token.

    Returns the new access_token string. Raises ``AuthenticationError`` on
    HTTP 4xx — the caller should surface that as 401 to the user with a
    "refresh your Salesforce credentials" message.
    """
    client_id = client_id or os.environ.get("SALESFORCE_CLIENT_ID", "")
    client_secret = client_secret or os.environ.get("SALESFORCE_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        raise ValidationFailed(
            "SALESFORCE_CLIENT_ID / SALESFORCE_CLIENT_SECRET must be configured "
            "to refresh Salesforce access tokens"
        )
    token_url = instance_url.rstrip("/") + "/services/oauth2/token"
    body = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    resp = httpx.post(token_url, data=body, timeout=timeout)
    if resp.status_code >= 400:
        raise AuthenticationError("Refresh Salesforce credentials")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise AuthenticationError("Refresh Salesforce credentials")
    return token


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------
class SalesforceRestClient:
    """Minimal Salesforce REST client — query + nextRecordsUrl pagination."""

    def __init__(
        self,
        instance_url: str,
        access_token: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = 30.0,
    ):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.api_version = api_version
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def query(self, soql: str, *, max_records: int = DEFAULT_MAX_RECORDS) -> Iterator[dict[str, Any]]:
        """Stream every record matching ``soql``, paginating via nextRecordsUrl.

        Raises ``AuthenticationError`` on 401, ``ValidationFailed`` on other 4xx.
        Stops once ``max_records`` rows have been yielded.
        """
        path = f"/services/data/{self.api_version}/query/"
        params: dict[str, str] | None = {"q": soql}
        url = self.instance_url + path
        yielded = 0
        while True:
            resp = httpx.get(url, params=params, headers=self._headers, timeout=self.timeout)
            if resp.status_code == 401:
                raise AuthenticationError("Refresh Salesforce credentials")
            if resp.status_code >= 400:
                raise ValidationFailed(
                    f"Salesforce query failed ({resp.status_code}): {resp.text[:200]}"
                )
            data = resp.json()
            for record in data.get("records", []) or []:
                yield record
                yielded += 1
                if yielded >= max_records:
                    return
            if data.get("done", True):
                return
            next_url = data.get("nextRecordsUrl")
            if not next_url:
                return
            url = self.instance_url + next_url
            params = None  # nextRecordsUrl already encodes the cursor


# ---------------------------------------------------------------------------
# Importer-shape helpers
# ---------------------------------------------------------------------------
def _flatten_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Salesforce record: drop the ``attributes`` envelope and
    expand the single ``Account.Name`` nested object into ``account_name``.

    Multi-level relationships (rare in our SOQL) are flattened with an
    underscore join — ``Account.Name`` → ``account_name`` — and the keys
    are lowercased so column_mapping.suggest() can match them.
    """
    flat: dict[str, Any] = {}
    for key, value in rec.items():
        if key == "attributes":
            continue
        if isinstance(value, dict):
            # one level of nesting (Account.Name)
            for sub_key, sub_val in value.items():
                if sub_key == "attributes":
                    continue
                flat[f"{key}_{sub_key}".lower()] = sub_val
        else:
            flat[key.lower()] = value
    return flat


def suggest_mapping_rest(source_columns: list[str], target_entity: str) -> dict[str, str]:
    """Same heuristic shape the CSV importer uses, with the REST-specific
    synonym table layered in."""
    return column_mapping.suggest(
        source_columns,
        target_entity,
        extra_synonyms=SF_REST_SYNONYMS.get(target_entity, {}),
    )


def _build_client_from_config(config: dict[str, Any]) -> SalesforceRestClient:
    instance_url = config.get("instance_url") or os.environ.get("SALESFORCE_INSTANCE_URL", "")
    if not instance_url:
        raise ValidationFailed("Salesforce REST mode requires an instance_url")
    access_token = config.get("access_token") or ""
    refresh_token = config.get("refresh_token") or ""
    if not access_token:
        if not refresh_token:
            raise AuthenticationError("Refresh Salesforce credentials")
        access_token = mint_access_token(
            instance_url,
            refresh_token,
            client_id=config.get("client_id"),
            client_secret=config.get("client_secret"),
        )
    return SalesforceRestClient(instance_url, access_token)


def fetch_records(
    target_entity: str,
    config: dict[str, Any],
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> Iterable[dict[str, Any]]:
    """Yield flattened dict rows for ``target_entity``."""
    soql = SOQL_BY_ENTITY.get(target_entity)
    if not soql:
        raise ValidationFailed(
            f"Salesforce REST mode does not support entity '{target_entity}'"
        )
    client = _build_client_from_config(config)
    for raw in client.query(soql, max_records=max_records):
        yield _flatten_record(raw)


# ---------------------------------------------------------------------------
# Commit path — mirrors csv_generic.CsvGenericImporter.import_rows but
# reads from the REST stream instead of a CSV file.
# ---------------------------------------------------------------------------
def import_rows_rest(job: ImportJob, db: Session, *, max_records: int = DEFAULT_MAX_RECORDS) -> ImportJob:
    """Commit Salesforce REST rows into the target entity."""
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

    from sqlalchemy import select  # local import to avoid a hard dep when unused
    from app.models.crm import Contact

    config = dict(job.config or {})

    try:
        rows = fetch_records(job.target_entity, config, max_records=max_records)
        for raw in rows:
            row_no += 1
            try:
                # column_mapping values reference the SOQL field names
                # (lowercased) — same _apply_mapping helper as CSV.
                mapped = _apply_mapping(raw, mapping)
                if "name" not in mapped:
                    first = mapped.pop("first_name", None)
                    last = mapped.pop("last_name", None)
                    composite = " ".join(p for p in (first, last) if p)
                    if composite:
                        mapped["name"] = composite

                if entity_key == "deal" and "contact_name" in mapped:
                    contact_name = mapped.pop("contact_name")
                    existing = db.scalar(select(Contact).where(Contact.name == contact_name))
                    if existing:
                        mapped["contact_id"] = existing.id

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
        # Surface auth failures distinctly — endpoint translates to 401.
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
    if strategy == "by_email":
        return (mapped.get("email") or "").lower() or None
    if strategy == "by_name":
        return (mapped.get("name") or "").lower() or None
    return None


def _find_existing(db: Session, model, mapped: dict[str, Any], strategy: str):
    from sqlalchemy import select

    if strategy == "by_email" and mapped.get("email"):
        return db.scalar(select(model).where(model.email == mapped["email"]))
    if strategy == "by_name" and mapped.get("name"):
        return db.scalar(select(model).where(model.name == mapped["name"]))
    return None


def is_rest_mode_configured(job_config: dict[str, Any] | None) -> bool:
    """True when this job's ``config`` carries enough info to use REST mode."""
    if not job_config:
        return False
    if not job_config.get("instance_url"):
        return False
    return bool(job_config.get("access_token") or job_config.get("refresh_token"))


def detect_columns(target_entity: str) -> list[str]:
    """Return the set of source columns the REST mode produces for the entity.

    Lets the suggest-mapping endpoint work without us having to hit
    Salesforce just to list field names.
    """
    soql = SOQL_BY_ENTITY.get(target_entity, "")
    # crude SELECT-field extraction
    after = soql.split("SELECT", 1)[-1].split("FROM", 1)[0]
    cols: list[str] = []
    for raw in after.split(","):
        token = raw.strip()
        if not token:
            continue
        if "." in token:
            # Account.Name -> account_name
            cols.append(token.replace(".", "_").lower())
        else:
            cols.append(token.lower())
    return cols
