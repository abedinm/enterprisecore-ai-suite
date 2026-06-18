"""Reusable Pydantic validators — the input-hardening layer.

Phase 2 goal: real users (and hostile ones) type garbage. Every write
endpoint should reject bad input with a *friendly* 422 before it reaches
the database, never crash, and never persist corrupt data.

These helpers are designed to be dropped onto schema fields via
``Annotated[...]`` or ``field_validator``. They are intentionally lenient
on optional/empty values (return as-is) and strict on malformed present
values.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# ISO 4217 — the currency codes we actually support. Extend as needed; an
# unknown code is rejected rather than silently stored.
SUPPORTED_CURRENCIES = {
    "USD", "EUR", "GBP", "SEK", "CHF", "CAD", "AUD", "JPY", "CNY", "INR",
    "BDT", "SGD", "AED", "SAR", "NZD", "NOK", "DKK", "ZAR", "BRL", "MXN",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# A pragmatic phone matcher — digits, spaces, +, -, parens, 6-32 chars.
_PHONE_RE = re.compile(r"^[\d\s()+\-]{6,32}$")


def validate_currency(value: str | None) -> str | None:
    """Normalise + validate an ISO-4217 currency code."""
    if value is None:
        return None
    v = value.strip().upper()
    if v == "":
        return "USD"
    if len(v) != 3 or not v.isalpha():
        raise ValueError("Currency must be a 3-letter ISO code, e.g. USD, EUR, GBP.")
    if v not in SUPPORTED_CURRENCIES:
        raise ValueError(
            f"Currency '{v}' isn't supported yet. "
            f"Supported: {', '.join(sorted(SUPPORTED_CURRENCIES))}."
        )
    return v


def validate_email_opt(value: str | None) -> str | None:
    """Validate an optional email; empty string → None."""
    if value is None:
        return None
    v = value.strip()
    if v == "":
        return None
    if len(v) > 255:
        raise ValueError("Email address is too long (max 255 characters).")
    if not _EMAIL_RE.match(v):
        raise ValueError("That doesn't look like a valid email address.")
    return v.lower()


def validate_phone_opt(value: str | None) -> str | None:
    """Validate an optional phone number; empty string → None."""
    if value is None:
        return None
    v = value.strip()
    if v == "":
        return None
    if not _PHONE_RE.match(v):
        raise ValueError("Phone number can only contain digits, spaces, and + - ( ).")
    return v


def non_negative_money(value: Decimal | int | float | str | None, field: str = "amount") -> Decimal:
    """Reject negative or non-numeric money values; coerce to Decimal."""
    if value is None:
        return Decimal("0")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field.capitalize()} must be a number.") from exc
    if d < 0:
        raise ValueError(f"{field.capitalize()} cannot be negative.")
    if d > Decimal("99999999999.99"):
        raise ValueError(f"{field.capitalize()} is unrealistically large.")
    return d


def positive_quantity(value: Decimal | int | float | str | None) -> Decimal:
    """Quantities must be > 0."""
    try:
        d = Decimal(str(value if value is not None else 1))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Quantity must be a number.") from exc
    if d <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if d > Decimal("1000000"):
        raise ValueError("Quantity is unrealistically large.")
    return d


def tax_rate_fraction(value: Decimal | int | float | str | None) -> Decimal:
    """Tax rate as a 0..1 fraction (e.g. 0.20). Reject out-of-range."""
    if value is None:
        return Decimal("0")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Tax rate must be a number.") from exc
    if d < 0 or d > 1:
        raise ValueError("Tax rate must be between 0 and 1 (e.g. 0.20 for 20%).")
    return d


def clamp_text(value: str | None, max_len: int, field: str = "field") -> str | None:
    """Reject text longer than max_len with a friendly message."""
    if value is None:
        return None
    if len(value) > max_len:
        raise ValueError(f"{field.capitalize()} is too long (max {max_len} characters).")
    return value
