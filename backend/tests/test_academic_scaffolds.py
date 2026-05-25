"""Smoke tests for the 9 scaffolded academic modules.

One create→list assertion per module so a typo or wiring regression is
caught fast, plus role-gating spot checks where the scaffold enforces them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests._academic_helpers import (
    get_user_id, make_class, make_room, make_semester, make_user, set_edu_plan,
)


API = "/api/v1/academic"


# ---------------------------------------------------------------------------
# LMS
# ---------------------------------------------------------------------------
def test_lms_create_and_list(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    r = client.post(
        f"{API}/lms/resources",
        headers=auth_headers,
        json={
            "title": "Lecture 1 slides",
            "resource_type": "slide",
            "url": "https://example.com/l1.pdf",
            "course_code": "CS101",
        },
    )
    assert r.status_code == 201, r.text
    list_r = client.get(f"{API}/lms/resources", headers=auth_headers)
    assert list_r.status_code == 200
    assert any(
        item["title"] == "Lecture 1 slides" for item in list_r.json()
    )


def test_lms_student_cannot_create(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "lms_student@local", "Student")
    r = client.post(
        f"{API}/lms/resources",
        headers=student_headers,
        json={
            "title": "Spam upload",
            "resource_type": "slide",
            "url": "https://example.com/x.pdf",
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Lab reports — owner-isolated
# ---------------------------------------------------------------------------
def test_lab_report_student_creates_and_lists_own(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "lr_teacher@local", "Teacher")
    student_headers = make_user(client, "lr_student@local", "Student")
    teacher_id = get_user_id("lr_teacher@local")
    semester = make_semester(client, auth_headers, name="Lab Semester")
    cls = make_class(
        client, auth_headers,
        teacher_id=teacher_id, semester_id=semester["id"],
        name="Lab Class", course_code="LR101",
    )
    r = client.post(
        f"{API}/lab/reports",
        headers=student_headers,
        json={"class_id": cls["id"], "title": "Lab 1 report"},
    )
    assert r.status_code == 201, r.text
    own = client.get(f"{API}/lab/reports", headers=student_headers)
    assert own.status_code == 200
    assert any(r["title"] == "Lab 1 report" for r in own.json())


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------
def test_exam_create_and_list(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    r = client.post(
        f"{API}/exams/",
        headers=auth_headers,
        json={
            "course_code": "CS101",
            "exam_date": "2026-05-20",
            "start_time": "09:00:00",
            "duration_min": 120,
            "syllabus_topics": ["loops", "recursion"],
            "difficulty": "medium",
        },
    )
    assert r.status_code == 201, r.text
    list_r = client.get(f"{API}/exams/", headers=auth_headers)
    assert any(e["course_code"] == "CS101" for e in list_r.json())


def test_exam_student_cannot_create(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "exam_student@local", "Student")
    r = client.post(
        f"{API}/exams/",
        headers=student_headers,
        json={
            "course_code": "X101",
            "exam_date": "2026-06-01",
            "start_time": "09:00:00",
            "syllabus_topics": [],
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Advising
# ---------------------------------------------------------------------------
def test_advising_create_and_list(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "adv_student@local", "Student")
    student_id = get_user_id("adv_student@local")
    advisor_headers = make_user(client, "adv_advisor@local", "Dean")
    advisor_id = get_user_id("adv_advisor@local")
    r = client.post(
        f"{API}/advising/sessions",
        headers=auth_headers,
        json={
            "student_id": student_id, "advisor_id": advisor_id,
            "scheduled_at": "2026-03-01T10:00:00+00:00",
            "notes": "First meeting",
            "credits_completed": 30, "credits_remaining": 90,
        },
    )
    assert r.status_code == 201, r.text
    # Student sees only their own session
    r2 = client.get(f"{API}/advising/sessions", headers=student_headers)
    assert r2.status_code == 200
    assert len(r2.json()) >= 1


# ---------------------------------------------------------------------------
# Group projects
# ---------------------------------------------------------------------------
def test_group_project_create_and_list(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "gp_teacher@local", "Teacher")
    teacher_id = get_user_id("gp_teacher@local")
    semester = make_semester(client, auth_headers, name="GP Semester")
    cls = make_class(
        client, auth_headers,
        teacher_id=teacher_id, semester_id=semester["id"],
        name="GP Class", course_code="GP101",
    )
    deadline = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    r = client.post(
        f"{API}/group/projects",
        headers=auth_headers,
        json={
            "name": "Capstone", "class_id": cls["id"],
            "description": "Build a thing", "deadline": deadline,
        },
    )
    assert r.status_code == 201, r.text
    list_r = client.get(f"{API}/group/projects", headers=auth_headers)
    assert any(p["name"] == "Capstone" for p in list_r.json())


# ---------------------------------------------------------------------------
# Study aids — calls AI gateway (mocked)
# ---------------------------------------------------------------------------
def test_study_aid_create_and_list(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "sa_student@local", "Student")
    r = client.post(
        f"{API}/study-aids/notes",
        headers=student_headers,
        json={"source_text": "Photosynthesis converts light into sugar."},
    )
    assert r.status_code == 201, r.text
    own = client.get(f"{API}/study-aids/notes", headers=student_headers)
    assert any(n["id"] == r.json()["id"] for n in own.json())


def test_study_aid_generate_uses_ai_gateway(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "sa_gen_student@local", "Student")
    fake_payload = {
        "summary": "Photosynthesis explained.",
        "flashcards": [{"front": "What is photosynthesis?",
                        "back": "Plants convert light to sugar"}],
        "mcqs": [{
            "question": "Photosynthesis uses…",
            "options": ["light", "darkness", "sound", "salt"],
            "answer_index": 0,
        }],
    }
    with patch("app.services.ai.smart_json", return_value=fake_payload):
        r = client.post(
            f"{API}/study-aids/notes/generate",
            headers=student_headers,
            json={"source_text": "Photosynthesis is..."},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["summary"] == "Photosynthesis explained."
    assert len(body["flashcards"]) == 1
    assert len(body["mcqs"]) == 1


# ---------------------------------------------------------------------------
# Study match
# ---------------------------------------------------------------------------
def test_study_profile_upsert_and_match(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    s1 = make_user(client, "sm_s1@local", "Student")
    s2 = make_user(client, "sm_s2@local", "Student")
    profile = {
        "university": "U1", "department": "CS", "semester": "Spring 2026",
        "courses": ["CS101", "CS201"], "goals": "ace the class",
        "preferred_time": "evenings", "study_style": "quiet",
        "online_only": False, "is_public": True,
    }
    r1 = client.post(f"{API}/study-match/profile", headers=s1, json=profile)
    assert r1.status_code == 201, r1.text
    r2 = client.post(f"{API}/study-match/profile", headers=s2, json=profile)
    assert r2.status_code == 201, r2.text
    matches = client.get(f"{API}/study-match/matches", headers=s1)
    assert matches.status_code == 200
    bodies = matches.json()
    assert len(bodies) >= 1
    assert bodies[0]["score"] > 0


# ---------------------------------------------------------------------------
# Finance — student owner isolation
# ---------------------------------------------------------------------------
def test_finance_record_owner_isolation(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    s1 = make_user(client, "fin_s1@local", "Student")
    s2 = make_user(client, "fin_s2@local", "Student")
    payload = {
        "kind": "expense", "amount": "12.34", "currency": "USD",
        "occurred_on": "2026-02-10", "category": "books",
    }
    r1 = client.post(f"{API}/finance/records", headers=s1, json=payload)
    assert r1.status_code == 201, r1.text
    r2 = client.get(f"{API}/finance/records", headers=s2)
    assert r2.status_code == 200
    # s2 sees their own (empty) list, not s1's record
    assert all(rec["id"] != r1.json()["id"] for rec in r2.json())


def test_scholarship_admin_only_write(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "sch_student@local", "Student")
    payload = {
        "name": "Merit Award", "provider": "School",
        "amount": "1000.00", "currency": "USD",
    }
    bad = client.post(
        f"{API}/finance/scholarships", headers=student_headers, json=payload,
    )
    assert bad.status_code == 403
    good = client.post(
        f"{API}/finance/scholarships", headers=auth_headers, json=payload,
    )
    assert good.status_code == 201, good.text


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------
def test_assignment_create_and_list(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "dl_teacher@local", "Teacher")
    teacher_id = get_user_id("dl_teacher@local")
    semester = make_semester(client, auth_headers, name="DL Semester")
    cls = make_class(
        client, auth_headers,
        teacher_id=teacher_id, semester_id=semester["id"],
        name="DL Class", course_code="DL101",
    )
    deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    r = client.post(
        f"{API}/deadlines/assignments",
        headers=auth_headers,
        json={
            "class_id": cls["id"], "title": "Homework 1",
            "deadline": deadline, "weight": "10",
        },
    )
    assert r.status_code == 201, r.text
    list_r = client.get(f"{API}/deadlines/assignments", headers=auth_headers)
    assert any(a["title"] == "Homework 1" for a in list_r.json())


def test_submission_student_owner_isolation(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "sub_teacher@local", "Teacher")
    s1 = make_user(client, "sub_s1@local", "Student")
    s2 = make_user(client, "sub_s2@local", "Student")
    teacher_id = get_user_id("sub_teacher@local")
    semester = make_semester(client, auth_headers, name="Sub Semester")
    cls = make_class(
        client, auth_headers,
        teacher_id=teacher_id, semester_id=semester["id"],
        name="Sub Class", course_code="SUB101",
    )
    deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    a = client.post(
        f"{API}/deadlines/assignments",
        headers=auth_headers,
        json={"class_id": cls["id"], "title": "HW1", "deadline": deadline},
    )
    assignment_id = a.json()["id"]
    sub_r = client.post(
        f"{API}/deadlines/submissions",
        headers=s1,
        json={
            "assignment_id": assignment_id, "status": "submitted",
            "word_count": 500, "submission_url": "https://example.com/s1",
        },
    )
    assert sub_r.status_code == 201, sub_r.text
    # s2 lists submissions for that assignment — sees nothing (owner-isolated)
    other = client.get(
        f"{API}/deadlines/submissions?assignment_id={assignment_id}",
        headers=s2,
    )
    assert other.status_code == 200
    assert all(s["student_id"] != sub_r.json()["student_id"]
               for s in other.json())
