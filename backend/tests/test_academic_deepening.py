"""Tests for the workflow features added on top of the academic scaffolds.

One test per new feature, mirroring the convention in test_academic_scaffolds.
AI calls are mocked via ``unittest.mock.patch`` so the suite runs offline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests._academic_helpers import (
    get_user_id, make_class, make_room, make_semester, make_user, set_edu_plan,
)


API = "/api/v1/academic"


# ---------------------------------------------------------------------------
# LMS — search, download counter, popular
# ---------------------------------------------------------------------------
def test_lms_search_filters(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    client.post(
        f"{API}/lms/resources",
        headers=auth_headers,
        json={
            "title": "Photosynthesis primer",
            "description": "Intro to chloroplasts",
            "resource_type": "note",
            "url": "https://example.com/photo.pdf",
            "course_code": "BIO101",
            "department": "Biology",
        },
    )
    client.post(
        f"{API}/lms/resources",
        headers=auth_headers,
        json={
            "title": "Algebra basics",
            "description": "Linear equations",
            "resource_type": "slide",
            "url": "https://example.com/alg.pdf",
            "course_code": "MATH101",
            "department": "Math",
        },
    )
    r = client.get(
        f"{API}/lms/resources/search?q=photo&department=Biology",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    titles = [item["title"] for item in r.json()]
    assert any("Photosynthesis" in t for t in titles)
    assert not any("Algebra" in t for t in titles)


def test_lms_download_increments_counter_and_popular(
    client, auth_headers, monkeypatch,
):
    set_edu_plan(monkeypatch)
    create = client.post(
        f"{API}/lms/resources",
        headers=auth_headers,
        json={
            "title": "Hot topic",
            "resource_type": "slide",
            "url": "https://example.com/hot.pdf",
        },
    )
    rid = create.json()["id"]
    # Three downloads — counter should land on 3 and resource should appear
    # at the top of /popular.
    for _ in range(3):
        d = client.post(
            f"{API}/lms/resources/{rid}/download",
            headers=auth_headers,
        )
        assert d.status_code == 200, d.text
    popular = client.get(
        f"{API}/lms/resources/popular?limit=5", headers=auth_headers,
    )
    assert popular.status_code == 200
    top = popular.json()
    assert top, "popular list should not be empty"
    assert top[0]["id"] == rid
    assert top[0]["download_count"] >= 3


# ---------------------------------------------------------------------------
# Lab reports — submit, grade, pending, summary
# ---------------------------------------------------------------------------
def test_lab_report_submit_transitions_status(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "lrd_teacher@local", "Teacher")
    student_headers = make_user(client, "lrd_student@local", "Student")
    teacher_id = get_user_id("lrd_teacher@local")
    semester = make_semester(client, auth_headers, name="LRD Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="LRD Class", course_code="LRD101",
    )
    create = client.post(
        f"{API}/lab/reports",
        headers=student_headers,
        json={"class_id": cls["id"], "title": "Lab one", "status": "draft"},
    )
    rid = create.json()["id"]
    r = client.post(
        f"{API}/lab/reports/{rid}/submit", headers=student_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted"
    # Second submit should be refused.
    r2 = client.post(
        f"{API}/lab/reports/{rid}/submit", headers=student_headers,
    )
    assert r2.status_code == 409


def test_lab_report_pending_for_teacher(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "lrp_teacher@local", "Teacher")
    student_headers = make_user(client, "lrp_student@local", "Student")
    teacher_id = get_user_id("lrp_teacher@local")
    semester = make_semester(client, auth_headers, name="LRP Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="LRP Class", course_code="LRP101",
    )
    # One report submitted, one still a draft. Only the submitted should appear.
    submitted = client.post(
        f"{API}/lab/reports", headers=student_headers,
        json={"class_id": cls["id"], "title": "Done", "status": "submitted"},
    ).json()
    client.post(
        f"{API}/lab/reports", headers=student_headers,
        json={"class_id": cls["id"], "title": "WIP", "status": "draft"},
    )
    r = client.get(
        f"{API}/lab/classes/{cls['id']}/pending", headers=teacher_headers,
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()]
    assert submitted["id"] in ids
    assert all(item["status"] == "submitted" for item in r.json())


def test_lab_report_student_summary(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "lrs_teacher@local", "Teacher")
    student_headers = make_user(client, "lrs_student@local", "Student")
    teacher_id = get_user_id("lrs_teacher@local")
    semester = make_semester(client, auth_headers, name="LRS Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="LRS Class", course_code="LRS101",
    )
    # Two graded reports, numeric grades 80 and 90 → avg 85.0.
    for grade in ("80", "90"):
        rep = client.post(
            f"{API}/lab/reports", headers=student_headers,
            json={"class_id": cls["id"], "title": f"R-{grade}"},
        ).json()
        client.post(
            f"{API}/lab/reports/{rep['id']}/grade",
            headers=teacher_headers,
            json={"grade": grade, "feedback": "ok"},
        )
    r = client.get(
        f"{API}/lab/students/me/summary", headers=student_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    classes = body["classes"]
    assert len(classes) == 1
    only = classes[0]
    assert only["class_id"] == cls["id"]
    assert only["total"] == 2
    assert only["by_status"]["graded"] == 2
    assert abs((only["avg_numeric_grade"] or 0) - 85.0) < 0.01


# ---------------------------------------------------------------------------
# Exams — schedule-room (with conflict), upcoming, by-room, calendar
# ---------------------------------------------------------------------------
def test_exam_schedule_room_detects_conflict(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    room_a = make_room(client, auth_headers, name="Exam Room A")
    # Two exams on the same day with overlapping windows.
    e1 = client.post(
        f"{API}/exams/", headers=auth_headers,
        json={
            "course_code": "EX101", "exam_date": "2026-06-01",
            "start_time": "09:00:00", "duration_min": 120,
            "syllabus_topics": [],
        },
    ).json()
    e2 = client.post(
        f"{API}/exams/", headers=auth_headers,
        json={
            "course_code": "EX102", "exam_date": "2026-06-01",
            "start_time": "10:00:00", "duration_min": 60,
            "syllabus_topics": [],
        },
    ).json()
    r1 = client.post(
        f"{API}/exams/{e1['id']}/schedule-room",
        headers=auth_headers, json={"room_id": room_a["id"]},
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"{API}/exams/{e2['id']}/schedule-room",
        headers=auth_headers, json={"room_id": room_a["id"]},
    )
    assert r2.status_code == 409, r2.text


def test_exam_upcoming_window(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    soon = (datetime.now(timezone.utc).date() + timedelta(days=3)).isoformat()
    later = (datetime.now(timezone.utc).date() + timedelta(days=60)).isoformat()
    client.post(
        f"{API}/exams/", headers=auth_headers,
        json={
            "course_code": "UP101", "exam_date": soon,
            "start_time": "09:00:00", "duration_min": 60,
            "syllabus_topics": [],
        },
    )
    client.post(
        f"{API}/exams/", headers=auth_headers,
        json={
            "course_code": "UP102", "exam_date": later,
            "start_time": "09:00:00", "duration_min": 60,
            "syllabus_topics": [],
        },
    )
    r = client.get(f"{API}/exams/upcoming?days=14", headers=auth_headers)
    assert r.status_code == 200, r.text
    codes = {e["course_code"] for e in r.json()}
    assert "UP101" in codes
    assert "UP102" not in codes


def test_exam_calendar_groups_by_date(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    client.post(
        f"{API}/exams/", headers=auth_headers,
        json={
            "course_code": "CAL1", "exam_date": "2026-07-10",
            "start_time": "09:00:00", "duration_min": 60,
            "syllabus_topics": [],
        },
    )
    client.post(
        f"{API}/exams/", headers=auth_headers,
        json={
            "course_code": "CAL2", "exam_date": "2026-07-10",
            "start_time": "11:00:00", "duration_min": 60,
            "syllabus_topics": [],
        },
    )
    r = client.get(f"{API}/exams/calendar?month=2026-07", headers=auth_headers)
    assert r.status_code == 200, r.text
    days = r.json()
    july_10 = [d for d in days if d["exam_date"] == "2026-07-10"]
    assert len(july_10) == 1
    assert len(july_10[0]["exams"]) >= 2


def test_exam_by_room(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    room = make_room(client, auth_headers, name="By-room Hall")
    exam = client.post(
        f"{API}/exams/", headers=auth_headers,
        json={
            "course_code": "BR101", "exam_date": "2026-08-15",
            "start_time": "09:00:00", "duration_min": 60,
            "syllabus_topics": [], "room_id": room["id"],
        },
    ).json()
    r = client.get(
        f"{API}/exams/by-room/{room['id']}?from=2026-08-01&to=2026-08-31",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert any(e["id"] == exam["id"] for e in r.json())


# ---------------------------------------------------------------------------
# Advising — CGPA trend, append notes, advisor upcoming, student history
# ---------------------------------------------------------------------------
def test_advising_cgpa_trend(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "cgpa_student@local", "Student")
    student_id = get_user_id("cgpa_student@local")
    advisor_id = get_user_id("admin@local")
    for at_iso, cgpa in (
        ("2026-01-15T10:00:00+00:00", "3.20"),
        ("2026-03-15T10:00:00+00:00", "3.40"),
        ("2026-05-15T10:00:00+00:00", "3.55"),
    ):
        client.post(
            f"{API}/advising/sessions", headers=auth_headers,
            json={
                "student_id": student_id, "advisor_id": advisor_id,
                "scheduled_at": at_iso,
                "current_cgpa": cgpa,
            },
        )
    r = client.get(
        f"{API}/advising/students/{student_id}/cgpa-trend",
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    # Should arrive in chronological order.
    cgpas = [p["current_cgpa"] for p in points]
    assert cgpas == ["3.20", "3.40", "3.55"]


def test_advising_append_notes(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "note_student@local", "Student")
    student_id = get_user_id("note_student@local")
    advisor_id = get_user_id("admin@local")
    session = client.post(
        f"{API}/advising/sessions", headers=auth_headers,
        json={
            "student_id": student_id, "advisor_id": advisor_id,
            "scheduled_at": "2026-04-01T10:00:00+00:00",
            "notes": "Initial.",
        },
    ).json()
    r = client.post(
        f"{API}/advising/sessions/{session['id']}/notes",
        headers=auth_headers, json={"text": "Follow-up scheduled."},
    )
    assert r.status_code == 200, r.text
    notes = r.json()["notes"]
    assert "Initial." in notes
    assert "Follow-up scheduled." in notes
    # Stamp should include the admin user's name.
    assert "Test Admin" in notes


def test_advising_advisor_upcoming(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    advisor_headers = make_user(client, "adv_up@local", "Dean")
    advisor_id = get_user_id("adv_up@local")
    student_id = get_user_id("admin@local")  # advisor's student is anyone
    soon = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    client.post(
        f"{API}/advising/sessions", headers=auth_headers,
        json={
            "student_id": student_id, "advisor_id": advisor_id,
            "scheduled_at": soon,
        },
    )
    r = client.get(
        f"{API}/advising/advisors/me/upcoming?days=30",
        headers=advisor_headers,
    )
    assert r.status_code == 200, r.text
    assert any(s["advisor_id"] == advisor_id for s in r.json())


# ---------------------------------------------------------------------------
# Group projects — auto-balance, fairness, active
# ---------------------------------------------------------------------------
def test_group_auto_balance_suggests_and_commits(
    client, auth_headers, monkeypatch,
):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "gpd_teacher@local", "Teacher")
    teacher_id = get_user_id("gpd_teacher@local")
    s1 = get_user_id(
        make_user(client, "gpd_s1@local", "Student") and "gpd_s1@local"
    )
    s2 = get_user_id(
        make_user(client, "gpd_s2@local", "Student") and "gpd_s2@local"
    )
    semester = make_semester(client, auth_headers, name="GPD Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="GPD Class", course_code="GPD101",
    )
    deadline = (datetime.now(timezone.utc) + timedelta(days=21)).isoformat()
    proj = client.post(
        f"{API}/group/projects", headers=auth_headers,
        json={
            "name": "Group A", "class_id": cls["id"], "deadline": deadline,
        },
    ).json()
    # Preview only — no persistence.
    preview = client.post(
        f"{API}/group/projects/{proj['id']}/auto-balance",
        headers=auth_headers,
        json={"student_ids": [s1, s2]},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["committed"] is False
    weights = [float(s["weight"]) for s in preview.json()["suggestions"]]
    assert abs(sum(weights) - 1.0) < 0.001
    # Commit — assignments should now exist.
    commit = client.post(
        f"{API}/group/projects/{proj['id']}/auto-balance?commit=true",
        headers=auth_headers,
        json={"student_ids": [s1, s2]},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["committed"] is True
    listing = client.get(
        f"{API}/group/assignments?project_id={proj['id']}",
        headers=auth_headers,
    )
    assert len(listing.json()) == 2


def test_group_fairness_flags_imbalance(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "gpf_teacher@local", "Teacher")
    teacher_id = get_user_id("gpf_teacher@local")
    s1 = get_user_id(
        make_user(client, "gpf_s1@local", "Student") and "gpf_s1@local"
    )
    s2 = get_user_id(
        make_user(client, "gpf_s2@local", "Student") and "gpf_s2@local"
    )
    semester = make_semester(client, auth_headers, name="GPF Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="GPF Class", course_code="GPF101",
    )
    deadline = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    proj = client.post(
        f"{API}/group/projects", headers=auth_headers,
        json={"name": "GP F", "class_id": cls["id"], "deadline": deadline},
    ).json()
    client.post(
        f"{API}/group/assignments", headers=auth_headers,
        json={
            "project_id": proj["id"], "student_id": s1,
            "role": "lead", "weight": "0.90",
        },
    )
    client.post(
        f"{API}/group/assignments", headers=auth_headers,
        json={
            "project_id": proj["id"], "student_id": s2,
            "role": "", "weight": "0.10",
        },
    )
    r = client.get(
        f"{API}/group/projects/{proj['id']}/fairness", headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balanced"] is False
    assert body["weight_std_dev"] > 0.05


def test_group_active_filters_future_deadline(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "gpa_teacher@local", "Teacher")
    teacher_id = get_user_id("gpa_teacher@local")
    semester = make_semester(client, auth_headers, name="GPA Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="GPA Class", course_code="GPA101",
    )
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    client.post(
        f"{API}/group/projects", headers=auth_headers,
        json={"name": "Future", "class_id": cls["id"], "deadline": future},
    )
    client.post(
        f"{API}/group/projects", headers=auth_headers,
        json={"name": "Past", "class_id": cls["id"], "deadline": past},
    )
    r = client.get(
        f"{API}/group/classes/{cls['id']}/active", headers=auth_headers,
    )
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Future" in names
    assert "Past" not in names


# ---------------------------------------------------------------------------
# Study aids — regenerate, quiz, attempts, history
# ---------------------------------------------------------------------------
def _seed_note_with_mcqs(client, student_headers):
    fake = {
        "summary": "Photosynthesis explained.",
        "flashcards": [{"front": "what?", "back": "answer"}],
        "mcqs": [
            {
                "question": "Photosynthesis uses?",
                "options": ["light", "darkness", "sound", "salt"],
                "answer_index": 0,
            },
            {
                "question": "Where does it happen?",
                "options": ["chloroplast", "nucleus", "ribosome", "lysosome"],
                "answer_index": 0,
            },
        ],
    }
    with patch("app.services.ai.smart_json", return_value=fake):
        r = client.post(
            f"{API}/study-aids/notes/generate",
            headers=student_headers,
            json={"source_text": "Photosynthesis is..."},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_study_aid_regenerate_overwrites(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "sar_student@local", "Student")
    note = _seed_note_with_mcqs(client, student_headers)
    better = {
        "summary": "Better summary.",
        "flashcards": [{"front": "q?", "back": "a"}],
        "mcqs": [
            {
                "question": "Updated question?",
                "options": ["a", "b", "c", "d"],
                "answer_index": 1,
            }
        ],
    }
    with patch("app.services.ai.smart_json", return_value=better):
        r = client.post(
            f"{API}/study-aids/notes/{note['id']}/regenerate",
            headers=student_headers,
            json={"hint": "more advanced"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] == "Better summary."
    assert body["mcqs"][0]["question"] == "Updated question?"


def test_study_aid_quiz_returns_questions_and_answer_key(
    client, auth_headers, monkeypatch,
):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "saq_student@local", "Student")
    note = _seed_note_with_mcqs(client, student_headers)
    r = client.get(
        f"{API}/study-aids/notes/{note['id']}/quiz", headers=student_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["questions"]) == 2
    # Answer key keys come back as JSON object keys → strings.
    assert body["answer_key"]["0"] == 0
    assert body["answer_key"]["1"] == 0


def test_study_aid_quiz_attempt_scoring_and_history(
    client, auth_headers, monkeypatch,
):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "sah_student@local", "Student")
    note = _seed_note_with_mcqs(client, student_headers)
    # Submit one right (idx 0 → answer 0) and one wrong (idx 1 → answer 2).
    r = client.post(
        f"{API}/study-aids/notes/{note['id']}/quiz/attempts",
        headers=student_headers,
        json={"answers": {"0": 0, "1": 2}},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["score"] == 1
    hist = client.get(
        f"{API}/study-aids/students/me/quiz-history",
        headers=student_headers,
    )
    assert hist.status_code == 200
    assert any(item["id"] == body["id"] for item in hist.json())


# ---------------------------------------------------------------------------
# Study buddies — refresh, top, connect, courses
# ---------------------------------------------------------------------------
def _profile_payload(courses):
    return {
        "university": "U1", "department": "CS", "semester": "Spring 2026",
        "courses": courses, "goals": "study together",
        "preferred_time": "evenings", "study_style": "quiet",
        "online_only": False, "is_public": True,
    }


def test_study_match_refresh_and_top(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    s1 = make_user(client, "smt_s1@local", "Student")
    s2 = make_user(client, "smt_s2@local", "Student")
    client.post(
        f"{API}/study-match/profile", headers=s1,
        json=_profile_payload(["CS101", "CS201"]),
    )
    client.post(
        f"{API}/study-match/profile", headers=s2,
        json=_profile_payload(["CS101", "CS201"]),
    )
    r = client.post(
        f"{API}/study-match/profiles/me/refresh-matches", headers=s1,
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) >= 1
    top = client.get(
        f"{API}/study-match/profiles/me/top-matches?limit=5", headers=s1,
    )
    assert top.status_code == 200, top.text
    rows = top.json()
    assert rows and rows[0]["score"] > 0
    assert "CS101" in rows[0]["shared_courses"]


def test_study_match_connect_creates_notification(
    client, auth_headers, monkeypatch,
):
    set_edu_plan(monkeypatch)
    s1 = make_user(client, "smc_s1@local", "Student")
    s2 = make_user(client, "smc_s2@local", "Student")
    client.post(
        f"{API}/study-match/profile", headers=s1,
        json=_profile_payload(["MATH101"]),
    )
    client.post(
        f"{API}/study-match/profile", headers=s2,
        json=_profile_payload(["MATH101"]),
    )
    matches = client.post(
        f"{API}/study-match/profiles/me/refresh-matches", headers=s1,
    ).json()
    assert matches
    match_id = matches[0]["id"]
    r = client.post(
        f"{API}/study-match/matches/{match_id}/connect", headers=s1,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["notification_id"]
    # Confirm the row landed in the notifications table for the right user.
    from sqlalchemy import select
    from app.models.user import Notification, User
    from tests.conftest import _TEST_DB
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    eng = create_engine(
        f"sqlite:///{_TEST_DB.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    sm = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    with sm() as db:
        s2_user = db.scalar(select(User).where(User.email == "smc_s2@local"))
        notif = db.get(Notification, body["notification_id"])
        assert notif is not None
        assert notif.user_id == s2_user.id


def test_study_match_courses_update_refreshes(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    s1 = make_user(client, "smcu_s1@local", "Student")
    s2 = make_user(client, "smcu_s2@local", "Student")
    client.post(
        f"{API}/study-match/profile", headers=s1,
        json=_profile_payload(["X100"]),
    )
    client.post(
        f"{API}/study-match/profile", headers=s2,
        json=_profile_payload(["CS101", "MATH101"]),
    )
    # Initial: no shared course → score should be modest.
    r0 = client.post(
        f"{API}/study-match/profiles/me/courses", headers=s1,
        json={"courses": ["PHIL101"]},
    )
    assert r0.status_code == 200, r0.text
    top0 = client.get(
        f"{API}/study-match/profiles/me/top-matches", headers=s1,
    ).json()
    initial_score = top0[0]["score"] if top0 else 0
    # Switch to shared courses → score should rise.
    r1 = client.post(
        f"{API}/study-match/profiles/me/courses", headers=s1,
        json={"courses": ["CS101", "MATH101"]},
    )
    assert r1.status_code == 200
    top1 = client.get(
        f"{API}/study-match/profiles/me/top-matches", headers=s1,
    ).json()
    assert top1 and top1[0]["score"] > initial_score


# ---------------------------------------------------------------------------
# Finance — summary, trend, budgets, status, scholarships upcoming
# ---------------------------------------------------------------------------
def test_finance_monthly_summary(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "fin_sum@local", "Student")
    for payload in (
        {"kind": "allowance", "amount": "1000.00", "occurred_on": "2026-04-05",
         "category": "income"},
        {"kind": "expense", "amount": "200.00", "occurred_on": "2026-04-10",
         "category": "food"},
        {"kind": "expense", "amount": "100.00", "occurred_on": "2026-04-15",
         "category": "books"},
    ):
        r = client.post(
            f"{API}/finance/records", headers=student_headers, json=payload,
        )
        assert r.status_code == 201, r.text
    r = client.get(
        f"{API}/finance/students/me/summary?month=2026-04",
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["total_allowance"]) == 1000.0
    assert float(body["total_expense"]) == 300.0
    assert float(body["net"]) == 700.0
    cats = {row["category"]: float(row["amount"])
            for row in body["expense_by_category"]}
    assert cats["food"] == 200.0
    assert cats["books"] == 100.0


def test_finance_trend_returns_six_points(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "fin_tr@local", "Student")
    r = client.get(
        f"{API}/finance/students/me/trend?months=6", headers=student_headers,
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["points"]) == 6


def test_finance_budget_crud_and_status(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "fin_bdg@local", "Student")
    r = client.post(
        f"{API}/finance/budgets", headers=student_headers,
        json={"category": "food", "monthly_limit": "150.00", "currency": "USD"},
    )
    assert r.status_code == 201, r.text
    # Duplicate category should 409.
    dupe = client.post(
        f"{API}/finance/budgets", headers=student_headers,
        json={"category": "food", "monthly_limit": "200.00", "currency": "USD"},
    )
    assert dupe.status_code == 409
    # Spend over the budget so /budget-status flags it.
    from datetime import datetime as _dt
    now = _dt.now(timezone.utc)
    today_iso = now.date().isoformat()
    client.post(
        f"{API}/finance/records", headers=student_headers,
        json={
            "kind": "expense", "amount": "180.00",
            "occurred_on": today_iso, "category": "food",
        },
    )
    month = f"{now.year:04d}-{now.month:02d}"
    status_r = client.get(
        f"{API}/finance/students/me/budget-status?month={month}",
        headers=student_headers,
    )
    assert status_r.status_code == 200, status_r.text
    rows = status_r.json()["rows"]
    food = next((row for row in rows if row["category"] == "food"), None)
    assert food is not None
    assert food["over_budget"] is True
    assert float(food["over_by"]) == 30.0


def test_finance_scholarships_upcoming(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "fin_sch@local", "Student")
    near = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    far = (datetime.now(timezone.utc).date() + timedelta(days=120)).isoformat()
    client.post(
        f"{API}/finance/scholarships", headers=auth_headers,
        json={"name": "Near", "amount": "500", "deadline": near},
    )
    client.post(
        f"{API}/finance/scholarships", headers=auth_headers,
        json={"name": "Far", "amount": "500", "deadline": far},
    )
    r = client.get(
        f"{API}/finance/scholarships/upcoming?days=60",
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    names = {s["name"] for s in r.json()}
    assert "Near" in names
    assert "Far" not in names


# ---------------------------------------------------------------------------
# Deadlines — upcoming, submit (upsert), status transition, late submissions
# ---------------------------------------------------------------------------
def test_deadlines_my_upcoming(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "dl_up_student@local", "Student")
    teacher_headers = make_user(client, "dl_up_teacher@local", "Teacher")
    teacher_id = get_user_id("dl_up_teacher@local")
    semester = make_semester(client, auth_headers, name="DLUp Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="DLUp Class", course_code="DLU101",
    )
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    far = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    client.post(
        f"{API}/deadlines/assignments", headers=auth_headers,
        json={"class_id": cls["id"], "title": "Soon HW", "deadline": soon},
    )
    client.post(
        f"{API}/deadlines/assignments", headers=auth_headers,
        json={"class_id": cls["id"], "title": "Far HW", "deadline": far},
    )
    r = client.get(
        f"{API}/deadlines/students/me/upcoming?days=14",
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    titles = {row["assignment"]["title"] for row in r.json()}
    assert "Soon HW" in titles
    assert "Far HW" not in titles


def test_deadlines_upsert_submission_is_idempotent(
    client, auth_headers, monkeypatch,
):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "dl_up2_student@local", "Student")
    teacher_id = get_user_id(
        make_user(client, "dl_up2_teacher@local", "Teacher")
        and "dl_up2_teacher@local"
    )
    semester = make_semester(client, auth_headers, name="DLUp2 Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="DLUp2 Class", course_code="DLU201",
    )
    deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    a = client.post(
        f"{API}/deadlines/assignments", headers=auth_headers,
        json={"class_id": cls["id"], "title": "HW", "deadline": deadline},
    ).json()
    first = client.post(
        f"{API}/deadlines/assignments/{a['id']}/submissions",
        headers=student_headers,
        json={"submission_url": "https://e.com/v1", "word_count": 100},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"{API}/deadlines/assignments/{a['id']}/submissions",
        headers=student_headers,
        json={"submission_url": "https://e.com/v2", "word_count": 250},
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["submission_url"] == "https://e.com/v2"
    assert second.json()["word_count"] == 250


def test_deadlines_status_forward_only_for_students(
    client, auth_headers, monkeypatch,
):
    set_edu_plan(monkeypatch)
    student_headers = make_user(client, "dl_st_student@local", "Student")
    teacher_id = get_user_id(
        make_user(client, "dl_st_teacher@local", "Teacher")
        and "dl_st_teacher@local"
    )
    semester = make_semester(client, auth_headers, name="DLSt Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="DLSt Class", course_code="DLS101",
    )
    deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    a = client.post(
        f"{API}/deadlines/assignments", headers=auth_headers,
        json={"class_id": cls["id"], "title": "HW", "deadline": deadline},
    ).json()
    sub = client.post(
        f"{API}/deadlines/submissions", headers=student_headers,
        json={"assignment_id": a["id"], "status": "submitted"},
    ).json()
    # Walking BACK to in_progress should 409 for a student.
    bad = client.patch(
        f"{API}/deadlines/submissions/{sub['id']}/status",
        headers=student_headers, json={"status": "in_progress"},
    )
    assert bad.status_code == 409, bad.text


def test_deadlines_late_submissions_for_teacher(client, auth_headers, monkeypatch):
    set_edu_plan(monkeypatch)
    teacher_headers = make_user(client, "dl_l_teacher@local", "Teacher")
    student_headers = make_user(client, "dl_l_student@local", "Student")
    teacher_id = get_user_id("dl_l_teacher@local")
    semester = make_semester(client, auth_headers, name="DLL Semester")
    cls = make_class(
        client, auth_headers, teacher_id=teacher_id,
        semester_id=semester["id"], name="DLL Class", course_code="DLL101",
    )
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    a = client.post(
        f"{API}/deadlines/assignments", headers=auth_headers,
        json={"class_id": cls["id"], "title": "Overdue HW", "deadline": past},
    ).json()
    # Student hasn't submitted yet — counts as late by status.
    client.post(
        f"{API}/deadlines/submissions", headers=student_headers,
        json={"assignment_id": a["id"], "status": "in_progress"},
    )
    r = client.get(
        f"{API}/deadlines/classes/{cls['id']}/late-submissions",
        headers=teacher_headers,
    )
    assert r.status_code == 200, r.text
    assert any(s["assignment_id"] == a["id"] for s in r.json())
