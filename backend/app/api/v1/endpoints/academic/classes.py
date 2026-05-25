"""Classes (course offerings) + enrollments.

Class CRUD is teacher/registrar/admin work; enrollment list/read is open to
the enrolled student, write is registrar/admin only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    REGISTRAR_OR_ADMIN, TEACHER_OR_ADMIN, _apply_update, _get_or_404,
    require_any_role,
)
from app.db.session import get_db
from app.models.academic.classes import (
    AcademicClass, AcademicClassEnrollment,
)
from app.models.user import User
from app.schemas.academic.classes import (
    ClassCreate, ClassOut, ClassUpdate, EnrollmentCreate, EnrollmentOut,
    EnrollmentUpdate,
)

router = APIRouter()


def _attach_teacher_name(db: Session, classes: list[AcademicClass]) -> list[AcademicClass]:
    """Populate the dynamic ``teacher_name`` attribute on each class so
    ``ClassOut`` can serialize it without forcing the caller to do an extra
    user lookup. Single bulk query for the whole list.
    """
    if not classes:
        return classes
    teacher_ids = {c.teacher_id for c in classes if c.teacher_id}
    teachers = {
        u.id: u.full_name
        for u in db.scalars(select(User).where(User.id.in_(teacher_ids))).all()
    }
    for c in classes:
        c.teacher_name = teachers.get(c.teacher_id)
    return classes


def _attach_one_teacher(db: Session, c: AcademicClass) -> AcademicClass:
    teacher = db.get(User, c.teacher_id) if c.teacher_id else None
    c.teacher_name = teacher.full_name if teacher else None
    return c


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[ClassOut])
def list_classes(
    semester_id: str | None = None,
    teacher_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(AcademicClass).order_by(AcademicClass.course_code)
    if semester_id:
        stmt = stmt.where(AcademicClass.semester_id == semester_id)
    if teacher_id:
        stmt = stmt.where(AcademicClass.teacher_id == teacher_id)
    classes = list(db.scalars(stmt).all())
    return _attach_teacher_name(db, classes)


@router.post(
    "/",
    response_model=ClassOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def create_class(payload: ClassCreate, db: Session = Depends(get_db)):
    obj = AcademicClass(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _attach_one_teacher(db, obj)


@router.get("/{class_id}", response_model=ClassOut)
def get_class(class_id: str, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    obj = _get_or_404(db, AcademicClass, class_id, "Class")
    return _attach_one_teacher(db, obj)


@router.patch(
    "/{class_id}",
    response_model=ClassOut,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def update_class(class_id: str, payload: ClassUpdate,
                 db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicClass, class_id, "Class")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return _attach_one_teacher(db, obj)


@router.delete(
    "/{class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def delete_class(class_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicClass, class_id, "Class")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------
@router.get("/{class_id}/enrollments", response_model=list[EnrollmentOut])
def list_enrollments(class_id: str, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    return db.scalars(
        select(AcademicClassEnrollment)
        .where(AcademicClassEnrollment.class_id == class_id)
        .order_by(AcademicClassEnrollment.enrolled_at)
    ).all()


@router.post(
    "/{class_id}/enrollments",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def enroll_student(
    class_id: str, payload: EnrollmentCreate, db: Session = Depends(get_db),
):
    # Force the URL-supplied class_id over whatever's in the body so the URL
    # is the canonical reference.
    data = payload.model_dump()
    data["class_id"] = class_id
    obj = AcademicClassEnrollment(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def update_enrollment(enrollment_id: str, payload: EnrollmentUpdate,
                      db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicClassEnrollment, enrollment_id, "Enrollment")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/enrollments/{enrollment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def delete_enrollment(enrollment_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicClassEnrollment, enrollment_id, "Enrollment")
    db.delete(obj)
    db.commit()
