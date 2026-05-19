"""Reusable pagination helper for list endpoints.

Usage
-----
    from app.api.pagination import PaginationParams, paginate

    @router.get("/items", response_model=Page[ItemOut])
    def list_items(
        params: PaginationParams = Depends(),
        db: Session = Depends(get_db),
    ):
        stmt = select(Item).order_by(Item.created_at.desc())
        return paginate(db, stmt, ItemOut, params)

Query string: `?page=2&page_size=50`. Page numbers are 1-based. Defaults are
1 / 25, with a hard ceiling of 200 per page so a hostile client can't request
50 000 rows in one go.
"""
from __future__ import annotations

from math import ceil
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PaginationParams:
    """FastAPI dependency. Injects ?page= and ?page_size= query params."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page index"),
        page_size: int = Query(25, ge=1, le=200, description="Items per page (1-200)"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(..., description="Total matching rows across all pages")
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def empty(cls, params: PaginationParams) -> "Page[T]":
        return cls(items=[], total=0, page=params.page, page_size=params.page_size, total_pages=0)


def paginate(
    db: Session,
    stmt: Select,
    schema: type[T],
    params: PaginationParams,
) -> Page[T]:
    """Run `stmt` once for COUNT(*) and once for the requested slice.

    `schema` is a Pydantic model with `model_config = ConfigDict(from_attributes=True)`
    (i.e. our `ORMModel` base) so SQLAlchemy rows convert directly.
    """
    # Count subquery is the safest cross-dialect approach for arbitrary stmts.
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    if total == 0:
        return Page[schema].empty(params)  # type: ignore[valid-type]

    rows = db.scalars(stmt.offset(params.offset).limit(params.limit)).all()
    items = [schema.model_validate(row) for row in rows]
    return Page[schema](  # type: ignore[valid-type]
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=ceil(total / params.page_size),
    )
