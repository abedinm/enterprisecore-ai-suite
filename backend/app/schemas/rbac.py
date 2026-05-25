"""Pydantic schemas for the granular RBAC API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PermissionOut(BaseModel):
    key: str
    category: str
    description: str


class CustomRoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    permission_keys: list[str] = Field(default_factory=list)


class CustomRoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    permission_keys: list[str] | None = None


class CustomRoleOut(ORMModel):
    id: str
    name: str
    description: str | None
    is_builtin: bool
    permission_keys: list[str]
    created_at: datetime
    updated_at: datetime


class BuiltInRoleOut(BaseModel):
    """A built-in :class:`UserRole` rendered as if it were a custom role —
    same response shape, but ``id`` is the enum value (e.g. ``"Admin"``)
    and ``is_builtin`` is True."""

    id: str
    name: str
    description: str | None = None
    is_builtin: bool = True
    permission_keys: list[str]


class RoleAssignmentIn(BaseModel):
    custom_role_id: str


class RoleAssignmentOut(ORMModel):
    id: str
    user_id: str
    custom_role_id: str
    created_at: datetime


class EffectivePermissionsOut(BaseModel):
    user_id: str
    built_in_role: str
    custom_role_ids: list[str]
    permission_keys: list[str]
