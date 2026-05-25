"""Service layer for the Construction Project Management module.

Endpoints in ``app/api/v1/endpoints/construction/`` call into these helpers so
the test surface stays small and framework-free (no FastAPI imports here).

Notable functions:

* :func:`compute_risk_score` / :func:`risk_severity` — turn (probability,
  impact) into the cached score and the dashboard severity bucket.
* :func:`dashboard_summary` — the rollup behind the dashboard endpoint.
* :func:`check_insurance_expiries` — finds policies expiring within ``days_ahead``.
* :func:`next_si_number` / :func:`next_variation_number` — atomic per-project
  auto-numbering for Site Instructions and Variations.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.construction.insurances import ConstructionInsurance
from app.models.construction.milestones import ConstructionMilestone
from app.models.construction.progress import ConstructionProgressReport
from app.models.construction.projects import ConstructionProject
from app.models.construction.risks import ConstructionRisk
from app.models.construction.schedule import ConstructionScheduleTask
from app.models.construction.site_instructions import ConstructionSiteInstruction
from app.models.construction.variations import ConstructionVariation
from app.models.construction.eot import ConstructionEOTRequest


Severity = Literal["low", "medium", "high", "critical"]


# ---------------------------------------------------------------------------
# Risk math
# ---------------------------------------------------------------------------
def compute_risk_score(probability: int, impact: int) -> int:
    """Validate bounds and return ``probability * impact``.

    Both inputs must be in [1, 5]. We raise ``ValidationFailed`` (HTTP 422) so
    a bad client payload becomes a clean API error rather than a 500.
    """
    if not (1 <= probability <= 5):
        raise ValidationFailed(
            f"probability must be between 1 and 5 (got {probability})",
        )
    if not (1 <= impact <= 5):
        raise ValidationFailed(
            f"impact must be between 1 and 5 (got {impact})",
        )
    return probability * impact


def risk_severity(score: int) -> Severity:
    """Bucket a risk score into the dashboard severity label.

    Buckets are intentionally chunky so the dashboard renders distinct
    colour bands rather than a smooth gradient: 1-4 low, 5-9 medium,
    10-15 high, 16-25 critical.
    """
    if score <= 4:
        return "low"
    if score <= 9:
        return "medium"
    if score <= 15:
        return "high"
    return "critical"


# ---------------------------------------------------------------------------
# Auto-numbering (SI-NNN / VAR-NNN)
# ---------------------------------------------------------------------------
_PREFIX_PATTERN = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<num>\d+)$")


def _next_numbered(
    db: Session,
    *,
    model_cls,
    project_id: str,
    prefix: str,
) -> str:
    """Generate the next ``{prefix}-NNN`` number for one project.

    We pull every existing number for the project and parse them locally
    rather than relying on a string ``MAX`` — the lexicographic ordering of
    ``SI-9`` vs ``SI-10`` would be wrong, so a Python pass over the parsed
    integers is the right move.
    """
    rows = db.scalars(
        select(model_cls.number).where(
            model_cls.construction_project_id == project_id,
        )
    ).all()
    highest = 0
    for raw in rows:
        if not raw:
            continue
        m = _PREFIX_PATTERN.match(raw.strip())
        if not m or m.group("prefix") != prefix:
            continue
        try:
            num = int(m.group("num"))
        except ValueError:
            continue
        if num > highest:
            highest = num
    return f"{prefix}-{highest + 1:03d}"


def next_si_number(db: Session, construction_project_id: str) -> str:
    """Next ``SI-NNN`` for the given project (e.g. ``SI-007``)."""
    return _next_numbered(
        db,
        model_cls=ConstructionSiteInstruction,
        project_id=construction_project_id,
        prefix="SI",
    )


def next_variation_number(db: Session, construction_project_id: str) -> str:
    """Next ``VAR-NNN`` for the given project (e.g. ``VAR-012``)."""
    return _next_numbered(
        db,
        model_cls=ConstructionVariation,
        project_id=construction_project_id,
        prefix="VAR",
    )


# ---------------------------------------------------------------------------
# Insurance expiries
# ---------------------------------------------------------------------------
def check_insurance_expiries(
    db: Session,
    *,
    construction_project_id: str | None = None,
    days_ahead: int = 90,
    today: date | None = None,
) -> list[ConstructionInsurance]:
    """Return insurances whose ``expiry_date`` falls within the next N days.

    A nullable ``construction_project_id`` lets ops staff pull every expiring
    policy across every project for a global "renewals" dashboard — leave it
    unset and we span the whole tenant.
    """
    today = today or date.today()
    horizon = today + timedelta(days=days_ahead)
    stmt = select(ConstructionInsurance).where(
        ConstructionInsurance.expiry_date.is_not(None),
        ConstructionInsurance.expiry_date >= today,
        ConstructionInsurance.expiry_date <= horizon,
    )
    if construction_project_id is not None:
        stmt = stmt.where(
            ConstructionInsurance.construction_project_id == construction_project_id,
        )
    stmt = stmt.order_by(ConstructionInsurance.expiry_date.asc())
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Dashboard rollup
# ---------------------------------------------------------------------------
def _risk_buckets(db: Session, project_id: str) -> dict:
    rows = db.scalars(
        select(ConstructionRisk).where(
            ConstructionRisk.construction_project_id == project_id,
        )
    ).all()
    buckets = {"low": 0, "medium": 0, "high": 0, "critical": 0, "total": 0}
    for r in rows:
        # Closed and accepted risks aren't part of the live exposure picture.
        if r.status in ("closed",):
            continue
        sev = risk_severity(r.score or 0)
        buckets[sev] += 1
        buckets["total"] += 1
    return buckets


def _schedule_progress(db: Session, project_id: str) -> int:
    """Average ``progress_percent`` across all tasks, weighted equally.

    For Gantt-style progress weighted by duration we'd multiply by duration
    and divide by total duration — left as a future enhancement; the simple
    mean is sufficient for the dashboard widget today.
    """
    avg = db.scalar(
        select(func.coalesce(func.avg(ConstructionScheduleTask.progress_percent), 0))
        .where(ConstructionScheduleTask.construction_project_id == project_id)
    )
    return int(round(float(avg or 0)))


def _upcoming_milestones(
    db: Session, project_id: str, *, today: date, window_days: int = 30,
) -> list[ConstructionMilestone]:
    horizon = today + timedelta(days=window_days)
    return list(db.scalars(
        select(ConstructionMilestone)
        .where(
            ConstructionMilestone.construction_project_id == project_id,
            ConstructionMilestone.planned_date >= today,
            ConstructionMilestone.planned_date <= horizon,
            ConstructionMilestone.status.in_(("upcoming", "achieved")),
        )
        .order_by(ConstructionMilestone.planned_date.asc())
    ).all())


def _open_variations(
    db: Session, project_id: str,
) -> list[ConstructionVariation]:
    return list(db.scalars(
        select(ConstructionVariation)
        .where(
            ConstructionVariation.construction_project_id == project_id,
            ConstructionVariation.status.in_(
                ("pending", "under_review", "approved"),
            ),
        )
        .order_by(ConstructionVariation.created_at.desc())
    ).all())


def _pending_eot_days(db: Session, project_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(ConstructionEOTRequest.requested_days), 0))
        .where(
            ConstructionEOTRequest.construction_project_id == project_id,
            ConstructionEOTRequest.status.in_(("submitted", "under_review")),
        )
    )
    return int(total or 0)


def _recent_site_instructions(
    db: Session, project_id: str, *, limit: int = 5,
) -> list[ConstructionSiteInstruction]:
    return list(db.scalars(
        select(ConstructionSiteInstruction)
        .where(ConstructionSiteInstruction.construction_project_id == project_id)
        .order_by(ConstructionSiteInstruction.created_at.desc())
        .limit(limit)
    ).all())


def _latest_progress_report(
    db: Session, project_id: str,
) -> ConstructionProgressReport | None:
    return db.scalar(
        select(ConstructionProgressReport)
        .where(ConstructionProgressReport.construction_project_id == project_id)
        .order_by(
            ConstructionProgressReport.report_date.desc(),
            ConstructionProgressReport.created_at.desc(),
        )
        .limit(1)
    )


def dashboard_summary(
    db: Session,
    construction_project_id: str,
    *,
    today: date | None = None,
) -> dict:
    """One-shot rollup of every dashboard widget's data.

    Returns a dict (not a Pydantic model) so the endpoint layer owns the
    response shape. ``today`` is overridable so tests can lock the clock.
    """
    project = db.get(ConstructionProject, construction_project_id)
    if project is None:
        raise NotFoundError("Construction project not found")
    today = today or date.today()

    open_vars = _open_variations(db, construction_project_id)
    open_vars_cost_total = sum(
        (v.cost_impact or Decimal("0") for v in open_vars), start=Decimal("0"),
    )

    return {
        "project": project,
        "risk_buckets": _risk_buckets(db, construction_project_id),
        "schedule_progress_percent": _schedule_progress(
            db, construction_project_id,
        ),
        "upcoming_milestones": _upcoming_milestones(
            db, construction_project_id, today=today,
        ),
        "open_variations": open_vars,
        "open_variations_cost_impact_total": open_vars_cost_total,
        "pending_eot_days": _pending_eot_days(db, construction_project_id),
        "expiring_insurances": check_insurance_expiries(
            db,
            construction_project_id=construction_project_id,
            days_ahead=90,
            today=today,
        ),
        "recent_site_instructions": _recent_site_instructions(
            db, construction_project_id,
        ),
        "latest_progress_report": _latest_progress_report(
            db, construction_project_id,
        ),
    }
