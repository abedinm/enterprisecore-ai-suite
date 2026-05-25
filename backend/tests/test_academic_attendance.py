"""Attendance — bulk marking, summary computation, report, role gating,
student-views-own-only.
"""
from __future__ import annotations

from datetime import date

from tests._academic_helpers import (
    get_user_id, make_class, make_room, make_semester, make_user, set_edu_plan,
)


API = "/api/v1/academic"


def _scaffold(client, auth_headers, monkeypatch):
    """Spin up plan + teacher + students + semester + class. Returns dict."""
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "att_teacher@local", "Teacher")
    student1_headers = make_user(client, "att_student1@local", "Student")
    student2_headers = make_user(client, "att_student2@local", "Student")
    teacher_id = get_user_id("att_teacher@local")
    s1 = get_user_id("att_student1@local")
    s2 = get_user_id("att_student2@local")

    semester = make_semester(client, auth_headers, name="Att Spring 2026")
    cls = make_class(
        client, auth_headers,
        teacher_id=teacher_id, semester_id=semester["id"],
        name="Attendance Test Class", course_code="AT101",
    )
    return {
        "teacher_headers": teacher_headers,
        "student1_headers": student1_headers,
        "student2_headers": student2_headers,
        "teacher_id": teacher_id,
        "s1": s1, "s2": s2,
        "semester": semester, "class": cls,
    }


def test_mark_attendance_creates_rows(client, auth_headers, monkeypatch):
    ctx = _scaffold(client, auth_headers, monkeypatch)
    r = client.post(
        f"{API}/classes/{ctx['class']['id']}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date(2026, 2, 1).isoformat(),
            "records": [
                {"student_id": ctx["s1"], "status": "present"},
                {"student_id": ctx["s2"], "status": "absent"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    rows = r.json()
    assert len(rows) == 2
    statuses = {row["student_id"]: row["status"] for row in rows}
    assert statuses[ctx["s1"]] == "present"
    assert statuses[ctx["s2"]] == "absent"


def test_mark_attendance_upserts_on_resubmit(
    client, auth_headers, monkeypatch,
):
    """Re-submitting for the same (class, student, date) overwrites rather
    than tripping the unique constraint."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    cls_id = ctx["class"]["id"]
    date_iso = date(2026, 2, 2).isoformat()
    # First mark — absent
    r = client.post(
        f"{API}/classes/{cls_id}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date_iso,
            "records": [{"student_id": ctx["s1"], "status": "absent"}],
        },
    )
    assert r.status_code == 201, r.text
    # Re-mark — present (correction)
    r2 = client.post(
        f"{API}/classes/{cls_id}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date_iso,
            "records": [{"student_id": ctx["s1"], "status": "present"}],
        },
    )
    assert r2.status_code == 201, r2.text
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "present"
    # Confirm only one row in the DB
    r3 = client.get(
        f"{API}/classes/{cls_id}/attendance?session_date={date_iso}",
        headers=ctx["teacher_headers"],
    )
    assert len(r3.json()) == 1


def test_get_session_attendance(client, auth_headers, monkeypatch):
    ctx = _scaffold(client, auth_headers, monkeypatch)
    cls_id = ctx["class"]["id"]
    date_iso = date(2026, 2, 3).isoformat()
    client.post(
        f"{API}/classes/{cls_id}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date_iso,
            "records": [
                {"student_id": ctx["s1"], "status": "late"},
                {"student_id": ctx["s2"], "status": "excused"},
            ],
        },
    )
    r = client.get(
        f"{API}/classes/{cls_id}/attendance?session_date={date_iso}",
        headers=ctx["teacher_headers"],
    )
    assert r.status_code == 200
    statuses = {row["student_id"]: row["status"] for row in r.json()}
    assert statuses == {ctx["s1"]: "late", ctx["s2"]: "excused"}


def test_class_attendance_report_computes_per_student_summary(
    client, auth_headers, monkeypatch,
):
    """Two sessions, two students — verify counts + percentage are right."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    cls_id = ctx["class"]["id"]
    # Session 1: s1 present, s2 absent
    client.post(
        f"{API}/classes/{cls_id}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date(2026, 2, 4).isoformat(),
            "records": [
                {"student_id": ctx["s1"], "status": "present"},
                {"student_id": ctx["s2"], "status": "absent"},
            ],
        },
    )
    # Session 2: both present
    client.post(
        f"{API}/classes/{cls_id}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date(2026, 2, 5).isoformat(),
            "records": [
                {"student_id": ctx["s1"], "status": "present"},
                {"student_id": ctx["s2"], "status": "present"},
            ],
        },
    )
    r = client.get(
        f"{API}/classes/{cls_id}/attendance/report",
        headers=ctx["teacher_headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by_student = {s["student_id"]: s for s in body["students"]}
    s1_sum = by_student[ctx["s1"]]
    assert s1_sum["present"] == 2
    assert s1_sum["absent"] == 0
    assert s1_sum["total"] == 2
    assert s1_sum["percentage"] == 100.0
    s2_sum = by_student[ctx["s2"]]
    assert s2_sum["present"] == 1
    assert s2_sum["absent"] == 1
    assert s2_sum["total"] == 2
    assert s2_sum["percentage"] == 50.0


def test_student_self_view_returns_only_own_records(
    client, auth_headers, monkeypatch,
):
    """A student hitting /students/me/attendance sees only their own rows."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    cls_id = ctx["class"]["id"]
    client.post(
        f"{API}/classes/{cls_id}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date(2026, 2, 6).isoformat(),
            "records": [
                {"student_id": ctx["s1"], "status": "present"},
                {"student_id": ctx["s2"], "status": "present"},
            ],
        },
    )
    r = client.get(
        f"{API}/students/me/attendance",
        headers=ctx["student1_headers"],
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    # Should only see s1's row, not s2's
    assert all(row["student_id"] == ctx["s1"] for row in rows)
    assert len(rows) >= 1


def test_student_cannot_view_other_student_attendance(
    client, auth_headers, monkeypatch,
):
    ctx = _scaffold(client, auth_headers, monkeypatch)
    r = client.get(
        f"{API}/students/{ctx['s2']}/attendance",
        headers=ctx["student1_headers"],
    )
    assert r.status_code == 403


def test_student_role_cannot_mark_attendance(
    client, auth_headers, monkeypatch,
):
    """Role gate — only teacher/admin can hit POST /attendance."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    r = client.post(
        f"{API}/classes/{ctx['class']['id']}/attendance",
        headers=ctx["student1_headers"],
        json={
            "session_date": date(2026, 2, 7).isoformat(),
            "records": [
                {"student_id": ctx["s1"], "status": "present"},
            ],
        },
    )
    assert r.status_code == 403


def test_teacher_can_view_specific_student_attendance(
    client, auth_headers, monkeypatch,
):
    ctx = _scaffold(client, auth_headers, monkeypatch)
    cls_id = ctx["class"]["id"]
    client.post(
        f"{API}/classes/{cls_id}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date(2026, 2, 8).isoformat(),
            "records": [{"student_id": ctx["s1"], "status": "present"}],
        },
    )
    r = client.get(
        f"{API}/students/{ctx['s1']}/attendance",
        headers=ctx["teacher_headers"],
    )
    assert r.status_code == 200


def test_invalid_status_rejected(client, auth_headers, monkeypatch):
    """A bad status enum is caught at the schema layer with a 422."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    r = client.post(
        f"{API}/classes/{ctx['class']['id']}/attendance",
        headers=ctx["teacher_headers"],
        json={
            "session_date": date(2026, 2, 9).isoformat(),
            "records": [{"student_id": ctx["s1"], "status": "WRONG"}],
        },
    )
    assert r.status_code == 422
