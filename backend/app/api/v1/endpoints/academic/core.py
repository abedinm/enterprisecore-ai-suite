"""Endpoints for academic semesters and rooms — registrar-managed primitives."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    REGISTRAR_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.academic.core import AcademicRoom, AcademicSemester
from app.schemas.academic.core import (
    RoomCreate, RoomOut, RoomUpdate, SemesterCreate, SemesterOut,
    SemesterUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Semesters
# ---------------------------------------------------------------------------
@router.get("/semesters", response_model=list[SemesterOut])
def list_semesters(db: Session = Depends(get_db),
                   _: object = Depends(get_current_user)):
    return db.scalars(
        select(AcademicSemester).order_by(AcademicSemester.start_date.desc())
    ).all()


@router.post(
    "/semesters",
    response_model=SemesterOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def create_semester(payload: SemesterCreate, db: Session = Depends(get_db)):
    if payload.is_current:
        # Only one current semester at a time — clear the flag on any sibling
        # before adding the new row.
        for row in db.scalars(
            select(AcademicSemester).where(AcademicSemester.is_current.is_(True))
        ).all():
            row.is_current = False
    obj = AcademicSemester(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/semesters/{obj_id}",
    response_model=SemesterOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def update_semester(obj_id: str, payload: SemesterUpdate,
                    db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicSemester, obj_id, "Semester")
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_current") is True:
        for row in db.scalars(
            select(AcademicSemester).where(
                AcademicSemester.is_current.is_(True),
                AcademicSemester.id != obj_id,
            )
        ).all():
            row.is_current = False
    _apply_update(obj, data)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/semesters/{obj_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def delete_semester(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicSemester, obj_id, "Semester")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------
@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db),
               _: object = Depends(get_current_user)):
    return db.scalars(
        select(AcademicRoom).order_by(AcademicRoom.name)
    ).all()


@router.post(
    "/rooms",
    response_model=RoomOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def create_room(payload: RoomCreate, db: Session = Depends(get_db)):
    obj = AcademicRoom(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/rooms/{obj_id}",
    response_model=RoomOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def update_room(obj_id: str, payload: RoomUpdate,
                db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicRoom, obj_id, "Room")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/rooms/{obj_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def delete_room(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicRoom, obj_id, "Room")
    db.delete(obj)
    db.commit()
