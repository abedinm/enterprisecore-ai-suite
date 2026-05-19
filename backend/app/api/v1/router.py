from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai, auth, coding, communication, crm, dashboard, documents, finance, hr,
    inventory, license, modules, notifications, projects, search, security_mod,
    settings, users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(modules.router, prefix="/modules", tags=["modules"])
api_router.include_router(finance.router, prefix="/finance", tags=["finance"])
api_router.include_router(hr.router, prefix="/hr", tags=["hr"])
api_router.include_router(crm.router, prefix="/crm", tags=["crm"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(communication.router, prefix="/communication", tags=["communication"])
api_router.include_router(security_mod.router, prefix="/security", tags=["security"])
api_router.include_router(coding.router, prefix="/coding", tags=["coding"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(license.router, prefix="/license", tags=["license"])
