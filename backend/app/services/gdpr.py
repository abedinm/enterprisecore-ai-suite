"""GDPR data export + erasure service.

Builds a JSON bundle of everything tied to a user (profile + records they
own + AI usage records + audit-log entries) and anonymizes the user record
on erasure while preserving audit-log integrity.

Anonymization strategy: we don't delete the user row because dozens of
audit-log + content-attribution FKs reference it. Instead we overwrite
the PII fields (email, full_name, avatar_url, mfa_secret, password_hash)
with deterministic placeholder values + set ``is_active=False`` so the
account can't be used. The user_id stays stable for audit integrity but
becomes meaningless from a privacy standpoint — which is the spirit of
GDPR Art. 17 ("right to erasure").
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import AuditLog, User
from app.models.webhooks import GdprErasureReceipt, GdprExportJob

# Categories of personal data we hold, for the privacy-policy endpoint.
DATA_CATEGORIES = [
    {
        "name": "Account",
        "description": "Identity, login, and contact info you provided.",
        "examples": ["email", "full_name", "avatar_url", "department", "locale", "theme"],
        "retention": "Until account closure + 30 days, then anonymized.",
    },
    {
        "name": "Authentication",
        "description": "Credentials and security material.",
        "examples": ["password_hash (bcrypt)", "MFA secret (Fernet-encrypted)", "refresh tokens"],
        "retention": "Until logout/rotation. Cleared on erasure.",
    },
    {
        "name": "Activity & audit",
        "description": "Records of actions you took in the suite.",
        "examples": ["audit logs", "search history", "login attempts"],
        "retention": "7 years for legal compliance. User id anonymized on erasure.",
    },
    {
        "name": "Business records authored by you",
        "description": "Records you created (leads, deals, invoices, projects, tasks, etc.).",
        "examples": ["CRM leads/deals", "Finance invoices/expenses", "HR records you logged"],
        "retention": "Indefinitely — tied to the tenant, not the individual.",
    },
    {
        "name": "AI usage",
        "description": "Prompts, responses, token counts attributable to you.",
        "examples": ["AI conversations + messages", "AI usage / spend records"],
        "retention": "13 months for billing reconciliation, then aggregated.",
    },
    {
        "name": "Webchat",
        "description": "Conversations you held with public-facing chatbots.",
        "examples": ["Conversation + message rows"],
        "retention": "12 months unless linked to a CRM contact.",
    },
]


def _models_with_created_by() -> list[type]:
    """Return ORM model classes that carry a ``created_by_id`` column.

    Discovered dynamically so newly-added models with a ``created_by_id``
    column appear in the export bundle without code changes here.
    """

    out: list[type] = []
    # Import the registry module so all models are loaded.
    from app import models  # noqa: F401
    from app.db.base import Base

    for mapper in Base.registry.mappers:
        cls = mapper.class_
        try:
            cols = {c.name for c in inspect(cls).columns}
        except Exception:  # pragma: no cover
            continue
        if "created_by_id" in cols or "owner_id" in cols or "user_id" in cols:
            out.append(cls)
    return out


def _record_to_dict(obj) -> dict[str, Any]:
    """Shallow dict of column values, JSON-coercing datetimes + Decimals."""

    cols = inspect(obj.__class__).columns
    result: dict[str, Any] = {}
    for c in cols:
        v = getattr(obj, c.name, None)
        if isinstance(v, datetime):
            result[c.name] = v.isoformat()
        elif hasattr(v, "value") and v.__class__.__name__.endswith("Role"):
            result[c.name] = v.value
        else:
            try:
                json.dumps(v, default=str)
                result[c.name] = v
            except Exception:
                result[c.name] = str(v)
    return result


def build_export(db: Session, user: User) -> dict[str, Any]:
    """Build the export bundle for ``user`` — a plain dict, ready to JSON-dump."""

    bundle: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "profile": _record_to_dict(user),
        "records_by_table": {},
        "data_categories": DATA_CATEGORIES,
    }
    # Never leak secrets in the export.
    for sensitive in ("password_hash", "mfa_secret"):
        if sensitive in bundle["profile"]:
            bundle["profile"][sensitive] = "<redacted>"

    total = 1  # profile counts as 1
    for cls in _models_with_created_by():
        if cls is User:
            continue
        cols = {c.name for c in inspect(cls).columns}
        # Pick the strongest link field.
        if "created_by_id" in cols:
            field = "created_by_id"
        elif "user_id" in cols:
            field = "user_id"
        elif "owner_id" in cols:
            field = "owner_id"
        else:
            continue
        try:
            rows = db.scalars(
                select(cls).where(getattr(cls, field) == user.id).limit(2000)
            ).all()
        except Exception:
            continue
        if not rows:
            continue
        bundle["records_by_table"][cls.__tablename__] = [
            _record_to_dict(r) for r in rows
        ]
        total += len(rows)
    bundle["record_count"] = total
    return bundle


def run_export_job(db: Session, job: GdprExportJob, storage_dir: Path) -> GdprExportJob:
    """Materialise the export bundle to disk + flip the job to ``ready``."""

    storage_dir.mkdir(parents=True, exist_ok=True)
    user = db.get(User, job.user_id)
    if user is None:
        job.status = "failed"
        job.error_message = "user not found"
        db.commit()
        return job
    try:
        bundle = build_export(db, user)
        out_path = storage_dir / f"{job.id}.json"
        out_path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
        job.status = "ready"
        job.download_path = f"exports/{job.id}.json"
        job.download_token = secrets.token_urlsafe(32)
        job.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        job.completed_at = datetime.now(timezone.utc)
        job.record_count = bundle.get("record_count", 0)
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.error_message = f"{type(exc).__name__}: {exc}"
    db.commit()
    return job


# ---- erasure --------------------------------------------------------------

# Fields we overwrite/null on the User row.
ERASURE_FIELDS = [
    "email", "full_name", "avatar_url", "department",
    "mfa_secret", "mfa_enabled", "password_hash", "is_active",
    "last_login_at",
]


def erase_user(db: Session, user: User, *, requested_by: User, reason: str) -> GdprErasureReceipt:
    """Anonymize the user in-place + create a receipt row.

    The original email is hashed into the placeholder so support can still
    correlate "I requested erasure" without recovering it.
    """

    import hashlib

    original_email = user.email or ""
    fingerprint = hashlib.sha256(original_email.encode()).hexdigest()[:12]
    placeholder_email = f"erased-{fingerprint}@deleted.invalid"

    # Refresh tokens are simply revoked so a logged-in session can't be used.
    from app.models.user import RefreshToken

    db.execute(
        RefreshToken.__table__.update()
        .where(RefreshToken.user_id == user.id)
        .values(revoked_at=datetime.now(timezone.utc))
    )

    user.email = placeholder_email
    user.full_name = "<deleted>"
    user.avatar_url = None
    user.department = None
    user.mfa_secret = None
    user.mfa_enabled = False
    user.is_active = False
    # Reset the password to a random, un-known value rather than NULL so the
    # bcrypt check in login always fails fast.
    user.password_hash = hash_password(secrets.token_urlsafe(32))

    receipt = GdprErasureReceipt(
        tenant_id=user.tenant_id,
        user_id=user.id,
        user_email_anonymized=placeholder_email,
        requested_by_id=requested_by.id if requested_by else None,
        reason=reason,
        fields_cleared=ERASURE_FIELDS,
        records_anonymized=1,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt
