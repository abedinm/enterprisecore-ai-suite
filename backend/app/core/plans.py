"""License plan → feature gating.

EnterpriseCore ships three SKUs:

* ``Core`` (default paid plan) — every always-on module plus webchat,
  marketing site builder, and the industry templates pack.
* ``+EDU`` — Core plus the academic module pack (attendance, timetable,
  LMS, lab reports, exam scheduling, etc.).
* ``+Verticals`` — Core plus extra industry template packs (future).

Evaluation mode (no LICENSE_KEY) gets the same feature set as ``Core`` so
prospects can fully demo the suite locally before paying. EDU stays gated
because it's a distinct vertical SKU, not a demo feature.

Module endpoints use ``require_plan_feature(name)`` (see ``app/api/deps.py``)
to enforce gating. The frontend reads ``/api/v1/license/features`` on boot
and hides nav items for disabled features.
"""
from __future__ import annotations

from enum import Enum


class Plan(str, Enum):
    EVALUATION = "evaluation"  # No LICENSE_KEY set
    CORE = "core"              # Standard paid plan
    EDU = "edu"                # Core + academic module pack
    VERTICALS = "verticals"    # Core + extra template packs


# Every module / sub-feature gated by the SKU system. Always-on platform
# features (auth, dashboard, settings, finance, hr, crm, projects, inventory,
# documents, communication, security, coding, ai brain, knowledge hub) are
# NOT listed here — they ship in every plan.
PLAN_FEATURES: dict[Plan, set[str]] = {
    Plan.EVALUATION: {"webchat", "marketing", "marketing_templates", "construction"},
    Plan.CORE:       {"webchat", "marketing", "marketing_templates"},
    Plan.EDU:        {"webchat", "marketing", "marketing_templates", "academic", "construction"},
    Plan.VERTICALS:  {"webchat", "marketing", "marketing_templates", "construction"},
}


def _plan_from_string(raw: str | None) -> Plan:
    """Coerce a plan string onto the Plan enum, defaulting to EVALUATION."""
    norm = (raw or "evaluation").strip().lower()
    try:
        return Plan(norm)
    except ValueError:
        if norm == "standard":
            return Plan.CORE
        return Plan.EVALUATION


def resolve_plan() -> Plan:
    """Resolve the active plan.

    Priority:
      1. If a tenant context is active AND the tenant has a non-default
         plan (anything other than "evaluation"), use that. A paid-tier
         tenant always gets its paid SKU regardless of the global license.
      2. Otherwise fall back to the global license key. An "evaluation"
         tenant on an EDU-licensed install gets EDU features — useful for
         single-tenant on-prem deployments that haven't migrated to
         per-tenant SKUs yet.

    Unknown plan names, missing license, and expired/invalid licenses all
    fall back to EVALUATION.
    """
    tenant_plan: Plan | None = None
    try:
        from app.core.tenant_context import get_current_tenant_id, bypass_tenant_filter
        tid = get_current_tenant_id()
        if tid:
            from app.db.session import SessionLocal
            from app.models.tenant import Tenant
            with bypass_tenant_filter(), SessionLocal() as db:
                tenant = db.get(Tenant, tid)
                if tenant:
                    tenant_plan = _plan_from_string(tenant.plan)
    except Exception:
        # Never crash plan resolution on a tenancy lookup error.
        pass

    # Resolve license too so we can pick the higher-tier of the two.
    from app.core.license_key import verify_license

    status = verify_license()
    if status.state in {"expired", "invalid"}:
        license_plan = Plan.EVALUATION
    else:
        license_plan = _plan_from_string(status.plan)

    # A non-default tenant plan always wins; otherwise fall back to license.
    if tenant_plan and tenant_plan is not Plan.EVALUATION:
        return tenant_plan
    return license_plan


def has_feature(feature: str) -> bool:
    """True when the resolved plan unlocks this feature name."""
    return feature in PLAN_FEATURES.get(resolve_plan(), set())


def enabled_features() -> set[str]:
    """All feature names the current plan unlocks."""
    return set(PLAN_FEATURES.get(resolve_plan(), set()))
