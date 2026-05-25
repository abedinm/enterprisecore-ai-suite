"""Shape for the construction dashboard rollup endpoint.

Returned by ``GET /api/v1/construction/projects/{id}/dashboard``. The frontend
hits this once when the dashboard mounts; every widget reads from the same
response so the UI doesn't have to fan-out 8 requests to render.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.schemas.construction.insurances import InsuranceOut
from app.schemas.construction.milestones import MilestoneOut
from app.schemas.construction.progress import ProgressReportOut
from app.schemas.construction.projects import ConstructionProjectOut
from app.schemas.construction.site_instructions import SiteInstructionOut
from app.schemas.construction.variations import VariationOut


class DashboardRiskBuckets(BaseModel):
    """Risk count grouped by computed severity (low/medium/high/critical)."""

    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0
    total: int = 0


class DashboardOut(BaseModel):
    """Everything the dashboard view needs in one response."""

    project: ConstructionProjectOut
    risk_buckets: DashboardRiskBuckets
    schedule_progress_percent: int
    upcoming_milestones: list[MilestoneOut]
    open_variations: list[VariationOut]
    open_variations_cost_impact_total: Decimal
    pending_eot_days: int
    expiring_insurances: list[InsuranceOut]
    recent_site_instructions: list[SiteInstructionOut]
    latest_progress_report: ProgressReportOut | None
