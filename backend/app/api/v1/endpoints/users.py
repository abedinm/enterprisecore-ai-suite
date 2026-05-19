"""User management endpoints (admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.pagination import Page, PaginationParams, paginate
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import AdminUserUpdate, UserCreate, UserRead

router = APIRouter()


@router.get("", response_model=list[UserRead], deprecated=True)
def list_users(
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Legacy unpaginated list — use ``GET /users/page`` instead. Capped at 500 rows."""
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    return db.scalars(stmt.order_by(User.created_at.desc()).limit(500)).all()


@router.get("/page", response_model=Page[UserRead])
def list_users_page(
    q: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    stmt = stmt.order_by(User.created_at.desc())
    return paginate(db, stmt, UserRead, pagination)


@router.post("", response_model=UserRead)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    if db.scalar(select(User).where(User.email == str(payload.email).lower())):
        raise ConflictError("A user with this email already exists")
    user = User(
        email=str(payload.email).lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            user.password_hash = hash_password(password)
    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_roles(UserRole.admin)),
):
    if user_id == current.id:
        raise ConflictError("You cannot delete your own account")
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    db.delete(user)
    db.commit()
    return None
