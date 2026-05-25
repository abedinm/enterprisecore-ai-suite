"""UserRole enum has the academic SKU roles + the original ones still work."""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import User, UserRole


# The four academic roles introduced in Phase 4.
ACADEMIC_ROLES = (UserRole.student, UserRole.teacher,
                  UserRole.registrar, UserRole.dean)
# Pre-existing roles must remain.
LEGACY_ROLES = (UserRole.admin, UserRole.manager,
                UserRole.employee, UserRole.developer)


def test_enum_has_eight_members():
    members = list(UserRole)
    assert len(members) == 8
    # All four legacy roles still present
    for r in LEGACY_ROLES:
        assert r in members
    # All four academic roles present
    for r in ACADEMIC_ROLES:
        assert r in members


def test_enum_string_values_match_titlecase():
    # The DB stores the human-readable form (string value of the enum)
    assert UserRole.student.value == "Student"
    assert UserRole.teacher.value == "Teacher"
    assert UserRole.registrar.value == "Registrar"
    assert UserRole.dean.value == "Dean"


def test_can_create_user_with_each_academic_role(db):
    """Each of the four new roles is acceptable on insert and round-trips."""
    for r in ACADEMIC_ROLES:
        email = f"role_{r.value.lower()}@local"
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(
                email=email,
                full_name=f"{r.value} User",
                password_hash=hash_password("ChangeMe123!"),
                role=r,
                is_active=True,
            ))
    db.commit()

    # Reload and verify the role round-tripped intact
    for r in ACADEMIC_ROLES:
        u = db.scalar(
            select(User).where(User.email == f"role_{r.value.lower()}@local"),
        )
        assert u is not None
        assert u.role == r


def test_legacy_roles_still_storable(db):
    """The four original roles must still work — regression guard."""
    for r in LEGACY_ROLES:
        email = f"legacy_{r.value.lower()}@local"
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(
                email=email,
                full_name=f"Legacy {r.value}",
                password_hash=hash_password("ChangeMe123!"),
                role=r,
                is_active=True,
            ))
    db.commit()
    for r in LEGACY_ROLES:
        u = db.scalar(
            select(User).where(User.email == f"legacy_{r.value.lower()}@local"),
        )
        assert u is not None
        assert u.role == r
