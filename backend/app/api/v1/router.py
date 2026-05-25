from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    ai, auth, billing, coding, communication, crm, dashboard, documents,
    encryption, finance, finance_consolidation, gamification, gdpr, hr,
    importers, inventory, jobs, knowledge, license, magic_link, marketing,
    modules, notifications, projects, rbac, scim, search, security_mod,
    security_policies, settings, sse, sso, tenants, users, webauthn, webchat, webhooks,
)
from app.api.v1.endpoints.academic import router as academic_router
from app.api.v1.endpoints.construction import router as construction_router
from app.core.rate_limit import write_rate_limit


def _writes(module: str):
    """Build the standard ``dependencies=[...]`` list for a business module.

    The dependency is a no-op for GET/HEAD and counts toward a per-module
    write bucket (60/minute) for POST/PUT/PATCH/DELETE. Applied at
    ``include_router`` so every route in the module inherits it.
    """
    return [Depends(write_rate_limit(module))]


api_router = APIRouter()
# /auth already has tighter per-endpoint limits (login, register, refresh).
# Other write endpoints (logout, /me PATCH, /me/avatar, /me/password, /mfa/*)
# go through a module-wide bucket so a stolen access token can't burn through
# them unimpeded.
api_router.include_router(auth.router, prefix="/auth", tags=["auth"], dependencies=_writes("auth"))
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"], dependencies=_writes("tenants"))
api_router.include_router(users.router, prefix="/users", tags=["users"], dependencies=_writes("users"))
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"], dependencies=_writes("settings"))
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"], dependencies=_writes("notifications"))
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(modules.router, prefix="/modules", tags=["modules"])
api_router.include_router(finance.router, prefix="/finance", tags=["finance"], dependencies=_writes("finance"))
# Phase 10 — multinational consolidation: subsidiary entities, intercompany
# transactions, consolidated balance sheet + P&L, FX revaluation. Mounted
# under /finance so the multi-entity surface sits next to the per-entity one.
api_router.include_router(
    finance_consolidation.router, prefix="/finance", tags=["finance"],
    dependencies=_writes("finance"),
)
api_router.include_router(hr.router, prefix="/hr", tags=["hr"], dependencies=_writes("hr"))
api_router.include_router(crm.router, prefix="/crm", tags=["crm"], dependencies=_writes("crm"))
api_router.include_router(projects.router, prefix="/projects", tags=["projects"], dependencies=_writes("projects"))
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"], dependencies=_writes("inventory"))
api_router.include_router(documents.router, prefix="/documents", tags=["documents"], dependencies=_writes("documents"))
api_router.include_router(communication.router, prefix="/communication", tags=["communication"], dependencies=_writes("communication"))
api_router.include_router(security_mod.router, prefix="/security", tags=["security"], dependencies=_writes("security"))
api_router.include_router(coding.router, prefix="/coding", tags=["coding"], dependencies=_writes("coding"))
api_router.include_router(ai.router, prefix="/ai", tags=["ai"], dependencies=_writes("ai"))
api_router.include_router(gamification.router, prefix="/gamification", tags=["gamification"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"], dependencies=_writes("knowledge"))
api_router.include_router(license.router, prefix="/license", tags=["license"], dependencies=_writes("license"))
api_router.include_router(billing.router, prefix="/billing", tags=["billing"], dependencies=_writes("billing"))
# Webchat already manages its own IP-keyed limits per public endpoint
# (``_PUBLIC_IP_LIMIT``) and a per-bot/per-session cap inside the handler.
# Layering a 60/min module limit on top would shadow the 120/min public cap
# the bot owner expects, so webchat opts out of the module bucket.
api_router.include_router(webchat.router, prefix="/webchat", tags=["webchat"])
api_router.include_router(marketing.router, prefix="/marketing", tags=["marketing"], dependencies=_writes("marketing"))
api_router.include_router(academic_router.router, prefix="/academic", tags=["academic"], dependencies=_writes("academic"))
api_router.include_router(construction_router.router, prefix="/construction", tags=["construction"], dependencies=_writes("construction"))

# Phase 7 identity layer — OIDC + SAML SSO, SCIM 2.0 token mgmt, magic-link.
# The SCIM protocol surface itself is mounted at the application root in
# main.py (under /scim/v2/) per RFC 7644; only the admin token-mgmt half
# lives here under /api/v1/sso/scim.
api_router.include_router(sso.router, prefix="/sso", tags=["sso"], dependencies=_writes("sso"))
api_router.include_router(scim.token_router, prefix="/sso/scim", tags=["sso"], dependencies=_writes("sso"))
api_router.include_router(magic_link.router, prefix="/auth", tags=["auth"], dependencies=_writes("auth"))

# WebAuthn passkeys — phishing-resistant 2FA / passwordless login.
# The /authenticate/* endpoints are public (used by sign-in), the
# /register/* + /credentials* endpoints require an existing session.
api_router.include_router(
    webauthn.router, prefix="/webauthn", tags=["auth"], dependencies=_writes("webauthn"),
)

# Phase 9 enterprise hardening — granular RBAC, BYOK encryption admin,
# tenant security policies (IP allowlist, audit stream destinations).
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"], dependencies=_writes("rbac"))
api_router.include_router(encryption.router, prefix="/encryption", tags=["security"], dependencies=_writes("encryption"))
# Mount under /security so the routes sit alongside the existing
# /security/* surface (vault, backups, compliance) the admin UI groups
# under one section.
api_router.include_router(security_policies.router, prefix="/security", tags=["security"], dependencies=_writes("security_policies"))

# Phase 8 — outbound webhooks + internal event bus + GDPR data export / erasure.
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"], dependencies=_writes("webhooks"))
api_router.include_router(gdpr.router, prefix="/gdpr", tags=["gdpr"], dependencies=_writes("gdpr"))

# Phase 9 — data migration importers (HubSpot / Salesforce / QuickBooks / CSV).
api_router.include_router(importers.router, prefix="/importers", tags=["importers"], dependencies=_writes("importers"))

# Phase 10 — background job queue admin observability (RQ-backed, sync
# fallback). All routes admin/manager-gated; cancel + retry are admin-only
# inside the endpoint module.
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"], dependencies=_writes("jobs"))

# Realtime — Server-Sent Events for job-status updates. SSE is the
# fallback transport for environments where WebSockets are blocked by
# a corporate proxy; the WS endpoints themselves are mounted in
# main.py.
api_router.include_router(sse.router, prefix="/sse", tags=["realtime"])

# Phase 8 mid-market integration layer — Slack / Google Workspace / Zapier
# connectors + the no-code workflow automation engine. The OAuth callback
# inside ``integrations`` is public (state-verified) but the rest of the
# surface honours the normal role gating defined in the endpoint code.
from app.api.v1.endpoints import integrations as integrations_ep, workflows as workflows_ep  # noqa: E402
api_router.include_router(
    integrations_ep.router, prefix="/integrations", tags=["integrations"],
    dependencies=_writes("integrations"),
)
api_router.include_router(
    workflows_ep.router, prefix="/workflows", tags=["workflows"],
    dependencies=_writes("workflows"),
)
