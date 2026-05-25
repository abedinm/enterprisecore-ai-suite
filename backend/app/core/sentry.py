"""Sentry SDK initialization for FastAPI backend.

No-op when SENTRY_DSN env var is unset, which is the default for tests and
local dev. Wired into the app lifespan in :mod:`app.main`.

Env vars consulted:
    SENTRY_DSN                       (required to enable)
    SENTRY_TRACES_SAMPLE_RATE        (float, default 0.1)
    SENTRY_PROFILES_SAMPLE_RATE      (float, default 0.1)
"""
from __future__ import annotations

import os

from loguru import logger

from app import __version__
from app.core.config import settings


def init_sentry() -> None:
    """Initialise Sentry if SENTRY_DSN is set; otherwise no-op."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.loguru import LoguruIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        # SDK not installed — silently skip so dev/test envs without the
        # optional extras still boot.
        logger.warning("SENTRY_DSN set but sentry-sdk not installed; skipping init")
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env,
        release=f"enterprisecore@{__version__}",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,  # GDPR — never auto-attach user IPs / emails
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            LoguruIntegration(),
        ],
    )
    logger.info("Sentry initialised (env={}, release=enterprisecore@{})", settings.app_env, __version__)
