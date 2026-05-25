"""Timetable — slot CRUD, conflict detection (room/teacher/class), schedule
queries, role gating.
"""
from __future__ import annotations

from tests._academic_helpers import (
    get_user_id, make_class, make_room, make_semester, make_user, set_edu_plan,
)


API = "/api/v1/academic"


def _scaffold(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_a_headers = make_user(client, "tt_teacher_a@local", "Teacher")
    teacher_b_headers = make_user(client, "tt_teacher_b@local", "Teacher")
    student_headers = make_user(client, "tt_student@local", "Student")
    registrar_headers = make_user(client, "tt_registrar@local", "Registrar")
    teacher_a_id = get_user_id("tt_teacher_a@local")
    teacher_b_id = get_user_id("tt_teacher_b@local")
    student_id = get_user_id("tt_student@local")

    semester = make_semester(client, auth_headers, name="TT Spring 2026")
    room_a = make_room(client, auth_headers, name="TT Room A")
    room_b = make_room(client, auth_headers, name="TT Room B")
    class_a = make_class(
        client, auth_headers,
        teacher_id=teacher_a_id, semester_id=semester["id"],
        name="TT Class A", course_code="TT101",
    )
    class_b = make_class(
        client, auth_headers,
        teacher_id=teacher_b_id, semester_id=semester["id"],
        name="TT Class B", course_code="TT102",
    )
    return {
        "teacher_a_headers": teacher_a_headers,
        "teacher_b_headers": teacher_b_headers,
        "student_headers": student_headers,
        "registrar_headers": registrar_headers,
        "teacher_a_id": teacher_a_id, "teacher_b_id": teacher_b_id,
        "student_id": student_id,
        "semester": semester,
        "room_a": room_a, "room_b": room_b,
        "class_a": class_a, "class_b": class_b,
    }


def test_create_slot_with_no_conflict(client, auth_headers, monkeypatch):
    ctx = _scaffold(client, auth_headers, monkeypatch)
    r = client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "10:30:00",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["room_id"] == ctx["room_a"]["id"]
    assert body["day_of_week"] == 0


def test_room_double_booking_returns_409(client, auth_headers, monkeypatch):
    """Two different classes in the same room at the same time → 409."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    # First booking — room A, Mon 09:00-10:30
    r1 = client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "10:30:00",
        },
    )
    assert r1.status_code == 201, r1.text
    # Second booking — different class, same room, overlapping window
    r2 = client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_b"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 0,
            "start_time": "10:00:00",
            "end_time": "11:30:00",
        },
    )
    assert r2.status_code == 409, r2.text
    assert "room" in r2.json()["detail"].lower()


def test_teacher_double_booking_returns_409(client, auth_headers, monkeypatch):
    """Same teacher in two different rooms at the same time → 409."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    # First booking — teacher A, room A, Mon 09:00-10:00
    client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
    )
    # Make a second class also taught by teacher_a so we can trigger the
    # teacher-double-book branch (rather than the class-double-book one).
    cls_a2 = make_class(
        client, auth_headers,
        teacher_id=ctx["teacher_a_id"],
        semester_id=ctx["semester"]["id"],
        name="TT Class A2", course_code="TT103",
    )
    r2 = client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": cls_a2["id"],
            "room_id": ctx["room_b"]["id"],  # different room
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 0,
            "start_time": "09:30:00",
            "end_time": "10:30:00",
        },
    )
    assert r2.status_code == 409, r2.text
    assert "teacher" in r2.json()["detail"].lower()


def test_class_double_booking_returns_409(client, auth_headers, monkeypatch):
    """Same class scheduled twice in overlapping windows → 409."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "10:30:00",
        },
    )
    r2 = client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],  # same class
            "room_id": ctx["room_b"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 0,
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        },
    )
    assert r2.status_code == 409, r2.text


def test_non_overlapping_slots_succeed(client, auth_headers, monkeypatch):
    """Same room, same day, but back-to-back times — no conflict."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    r1 = client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 1,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_b"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 1,
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        },
    )
    assert r2.status_code == 201, r2.text


def test_student_role_cannot_create_slot(client, auth_headers, monkeypatch):
    ctx = _scaffold(client, auth_headers, monkeypatch)
    r = client.post(
        f"{API}/timetable/slots",
        headers=ctx["student_headers"],
        json={
            "class_id": ctx["class_a"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 2,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
    )
    assert r.status_code == 403


def test_teacher_personal_schedule(client, auth_headers, monkeypatch):
    """A teacher hitting /teachers/me/schedule only sees their own classes."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],  # taught by teacher_a
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 3,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
    )
    client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_b"]["id"],  # taught by teacher_b
            "room_id": ctx["room_b"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 3,
            "start_time": "11:00:00",
            "end_time": "12:00:00",
        },
    )
    r = client.get(
        f"{API}/timetable/teachers/me/schedule?semester_id={ctx['semester']['id']}",
        headers=ctx["teacher_a_headers"],
    )
    assert r.status_code == 200
    slots = r.json()
    # Teacher A only sees class_a's slot
    class_ids = {s["class_id"] for s in slots}
    assert class_ids == {ctx["class_a"]["id"]}


def test_student_schedule_via_enrollment(client, auth_headers, monkeypatch):
    """Student schedule is derived from their active enrollments."""
    ctx = _scaffold(client, auth_headers, monkeypatch)
    # Enroll the student in class_a
    r = client.post(
        f"{API}/classes/{ctx['class_a']['id']}/enrollments",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],
            "student_id": ctx["student_id"],
            "status": "active",
        },
    )
    assert r.status_code == 201, r.text
    # Schedule the class
    client.post(
        f"{API}/timetable/slots",
        headers=auth_headers,
        json={
            "class_id": ctx["class_a"]["id"],
            "room_id": ctx["room_a"]["id"],
            "semester_id": ctx["semester"]["id"],
            "day_of_week": 4,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
    )
    r2 = client.get(
        f"{API}/timetable/students/me/schedule?semester_id={ctx['semester']['id']}",
        headers=ctx["student_headers"],
    )
    assert r2.status_code == 200
    slots = r2.json()
    assert len(slots) >= 1
    assert any(s["class_id"] == ctx["class_a"]["id"] for s in slots)
