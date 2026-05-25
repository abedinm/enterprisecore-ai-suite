"""Provider-agnostic email sender.

One ``send_email`` entry point, four backends, switched purely by the
``EMAIL_PROVIDER`` env var. The default ``console`` provider just dumps the
message to the application log — perfect for local development and the
default test mode, where we never want to make a real network call.

Why this lives as a tiny service instead of leaning on a SaaS SDK directly:
many enterprise customers self-host the suite and need to use whatever
gateway IT has already approved (Postfix relay, SES, on-prem SMTP). Hiding
the choice behind one interface means every caller (magic-link, invites,
password reset, future digest emails) writes against the same surface and
the deployment team flips one env var.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Callable

from loguru import logger


@dataclass
class SentEmail:
    """Captured email — used in tests to assert what would have been sent."""

    to: str
    subject: str
    body_text: str
    body_html: str | None = None
    reply_to: str | None = None
    from_addr: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


# Test capture buffer. Populated by the ``console`` and ``capture`` providers.
# Tests reset this via ``reset_captured()`` between cases.
_CAPTURED: list[SentEmail] = []


def reset_captured() -> None:
    """Clear the in-memory email capture. Called from test fixtures."""
    _CAPTURED.clear()


def get_captured() -> list[SentEmail]:
    """Return a copy of the captured email list — safe to iterate without
    worrying about concurrent modification."""
    return list(_CAPTURED)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _provider_console(msg: SentEmail) -> None:
    """Log + capture. Used in dev and tests."""
    logger.info(
        "[EMAIL → {}] {} | {}",
        msg.to,
        msg.subject,
        msg.body_text[:200].replace("\n", " ") + ("…" if len(msg.body_text) > 200 else ""),
    )
    _CAPTURED.append(msg)


def _provider_smtp(msg: SentEmail) -> None:
    """RFC 5321 SMTP via stdlib. TLS by default."""
    host = os.environ.get("SMTP_HOST", "localhost")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    em = EmailMessage()
    em["Subject"] = msg.subject
    em["From"] = msg.from_addr or os.environ.get("EMAIL_FROM", "noreply@localhost")
    em["To"] = msg.to
    if msg.reply_to:
        em["Reply-To"] = msg.reply_to
    em.set_content(msg.body_text)
    if msg.body_html:
        em.add_alternative(msg.body_html, subtype="html")

    with smtplib.SMTP(host, port, timeout=20) as s:
        if use_tls:
            s.starttls()
        if user and password:
            s.login(user, password)
        s.send_message(em)


def _provider_sendgrid(msg: SentEmail) -> None:  # pragma: no cover  — network
    """SendGrid REST API. Hidden behind an import-time check so we don't
    force the dependency when it's not in use."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY not set")
    try:
        import httpx
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("httpx is required for the SendGrid provider") from exc

    from_addr = msg.from_addr or os.environ.get("EMAIL_FROM", "noreply@localhost")
    payload: dict = {
        "personalizations": [{"to": [{"email": msg.to}]}],
        "from": {"email": from_addr},
        "subject": msg.subject,
        "content": [{"type": "text/plain", "value": msg.body_text}],
    }
    if msg.body_html:
        payload["content"].append({"type": "text/html", "value": msg.body_html})
    if msg.reply_to:
        payload["reply_to"] = {"email": msg.reply_to}

    resp = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()


def _provider_ses(msg: SentEmail) -> None:  # pragma: no cover  — network
    """Amazon SES via boto3. Picks credentials up from the usual env/instance
    role chain so callers don't have to plumb anything explicit."""
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for the SES provider") from exc

    client = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    body: dict = {"Text": {"Data": msg.body_text}}
    if msg.body_html:
        body["Html"] = {"Data": msg.body_html}
    client.send_email(
        Source=msg.from_addr or os.environ.get("EMAIL_FROM", "noreply@localhost"),
        Destination={"ToAddresses": [msg.to]},
        Message={"Subject": {"Data": msg.subject}, "Body": body},
        ReplyToAddresses=[msg.reply_to] if msg.reply_to else [],
    )


_PROVIDERS: dict[str, Callable[[SentEmail], None]] = {
    "console": _provider_console,
    "smtp": _provider_smtp,
    "sendgrid": _provider_sendgrid,
    "ses": _provider_ses,
}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def send_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    reply_to: str | None = None,
    *,
    from_addr: str | None = None,
) -> SentEmail:
    """Send (or capture) one email. Never raises on transport errors in the
    default ``console`` provider — production deployments using SMTP/SES/
    SendGrid should set up retry/dead-letter handling around this in the
    caller if delivery guarantees are required.

    Returns the ``SentEmail`` record so callers can log/debug what they
    just emitted.
    """
    provider_name = os.environ.get("EMAIL_PROVIDER", "console").lower()
    provider = _PROVIDERS.get(provider_name, _provider_console)
    from_addr = from_addr or os.environ.get("EMAIL_FROM", "noreply@enterprisecore.local")
    msg = SentEmail(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        reply_to=reply_to,
        from_addr=from_addr,
    )
    try:
        provider(msg)
    except Exception as exc:
        logger.exception("Email provider {!r} failed for to={}: {}", provider_name, to, exc)
        # Capture even on failure so test asserts that inspect captured
        # don't blow up when a misconfigured provider is in play.
        if provider_name != "console":
            _CAPTURED.append(msg)
        # Re-raise only in production — dev/tests should keep going.
        if provider_name not in ("console",) and os.environ.get("APP_ENV") == "production":
            raise
    return msg
