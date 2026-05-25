"""Parent router for the Construction Project Management module.

Every sub-router under this file inherits the
``require_plan_feature("construction")`` dependency from the parent, so
removing the construction feature from the active plan disappears every
endpoint with one switch flip.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_plan_feature
from app.api.v1.endpoints.construction import (
    contracts, eot, insurances, milestones, permits, progress, projects, raci,
    risks, schedule, site_instructions, toolbox, variations,
)

router = APIRouter(
    dependencies=[Depends(require_plan_feature("construction"))],
)

# Top-level ConstructionProject CRUD + dashboard rollup.
router.include_router(projects.router, tags=["construction-projects"])
router.include_router(risks.router, tags=["construction-risks"])
router.include_router(schedule.router, tags=["construction-schedule"])
router.include_router(milestones.router, tags=["construction-milestones"])
router.include_router(progress.router, tags=["construction-progress"])
router.include_router(permits.router, tags=["construction-permits"])
router.include_router(
    site_instructions.router, tags=["construction-site-instructions"],
)
router.include_router(variations.router, tags=["construction-variations"])
router.include_router(eot.router, tags=["construction-eot"])
router.include_router(contracts.router, tags=["construction-contracts"])
router.include_router(raci.router, tags=["construction-raci"])
router.include_router(insurances.router, tags=["construction-insurances"])
router.include_router(toolbox.router, tags=["construction-toolbox"])
