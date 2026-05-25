"""Construction Project Management — SQLAlchemy models.

Imported once from app/models/__init__.py so SQLAlchemy's declarative base
sees every construction_* table. Submodules are split by domain so each file
is small enough to read end-to-end while writing service logic.

The :class:`ConstructionProject` row is the construction-industry-specific
project record; it can optionally link back to the generic :class:`Project`
in ``app/models/projects.py`` via ``generic_project_id`` when the customer
already created a Project under the always-on Projects module.
"""
from app.models.construction.contracts import ConstructionContract  # noqa: F401
from app.models.construction.eot import ConstructionEOTRequest  # noqa: F401
from app.models.construction.insurances import ConstructionInsurance  # noqa: F401
from app.models.construction.milestones import ConstructionMilestone  # noqa: F401
from app.models.construction.permits import ConstructionPermit  # noqa: F401
from app.models.construction.progress import ConstructionProgressReport  # noqa: F401
from app.models.construction.projects import ConstructionProject  # noqa: F401
from app.models.construction.raci import ConstructionRaciEntry  # noqa: F401
from app.models.construction.risks import ConstructionRisk  # noqa: F401
from app.models.construction.schedule import (  # noqa: F401
    ConstructionScheduleDependency, ConstructionScheduleTask,
)
from app.models.construction.site_instructions import (  # noqa: F401
    ConstructionSiteInstruction,
)
from app.models.construction.toolbox import ConstructionToolboxTalk  # noqa: F401
from app.models.construction.variations import ConstructionVariation  # noqa: F401

__all__ = [
    "ConstructionContract",
    "ConstructionEOTRequest",
    "ConstructionInsurance",
    "ConstructionMilestone",
    "ConstructionPermit",
    "ConstructionProgressReport",
    "ConstructionProject",
    "ConstructionRaciEntry",
    "ConstructionRisk",
    "ConstructionScheduleDependency",
    "ConstructionScheduleTask",
    "ConstructionSiteInstruction",
    "ConstructionToolboxTalk",
    "ConstructionVariation",
]
