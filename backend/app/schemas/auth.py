from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import UserRole
from app.schemas.common import ORMModel


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)  # accept local-only emails like admin@local
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10, max_length=128)
    role: UserRole = UserRole.employee
    department: str | None = Field(default=None, max_length=120)
    locale: str | None = Field(default="en", max_length=12)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    department: str | None = Field(default=None, max_length=120)
    locale: str | None = Field(default=None, max_length=12)
    theme: str | None = Field(default=None, max_length=16)
    avatar_url: str | None = Field(default=None, max_length=500)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)  # accept local-only emails like admin@local
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class UserRead(ORMModel):
    id: str
    email: str
    full_name: str
    role: UserRole
    department: str | None = None
    avatar_url: str | None = None
    theme: str
    locale: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
