"""Regression tests that pin the query budget for hot endpoints.

These tests don't measure latency — they count SQL statements via
``app.services.query_perf.count_queries`` and assert the count stays
under a budget. The budgets are set just above what the current
optimized code achieves, so a future change that reintroduces an N+1
fires the alarm.

Budgets were derived by:
1.  Calling the endpoint on a populated dataset (created in-test).
2.  Recording the count returned by ``count_queries``.
3.  Setting the budget to ``measured + 2`` for resilience against tiny
    refactors (e.g. an extra auth lookup).

If you legitimately need to raise a budget, do it in the same PR as
the code change and explain why in the message.
"""
from __future__ import annotations

import pytest

from app.core.cache import _MemoryBackend, set_backend
from app.models.projects import Project, Task
from app.services.query_perf import count_queries


@pytest.fixture(autouse=True)
def _disable_response_cache():
    """Force a fresh cache for every test so we measure the actual
    DB roundtrip count, not "is it cached"."""
    set_backend(_MemoryBackend())
    yield
    set_backend(_MemoryBackend())


def _seed_projects_with_tasks(db, n_projects: int = 5, tasks_each: int = 4):
    """Build a project dataset that would balloon an N+1 endpoint."""
    projects = []
    for i in range(n_projects):
        p = Project(name=f"P{i}", status="active", color="#000000")
        db.add(p)
        db.flush()
        for j in range(tasks_each):
            db.add(Task(
                project_id=p.id,
                title=f"T{i}-{j}",
                status="done" if j == 0 else "todo",
                priority="medium",
            ))
        projects.append(p)
    db.commit()
    return projects


def test_root_dashboard_query_budget(client, auth_headers, engine):
    """/api/v1/dashboard rolls up cross-module KPIs but uses aggregates only.
    No collection traversal → tight budget."""
    with count_queries(engine) as q:
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    # Auth lookup + ~6 aggregate scalars. Budget = 12 leaves room for
    # tenant context probes and the user-load join chain.
    assert q.count <= 12, (
        f"/dashboard fired {q.count} queries — N+1 regression?\n"
        f"{q.by_table()}"
    )


def test_finance_dashboard_query_budget(client, auth_headers, engine):
    """/api/v1/finance/reports/dashboard runs ~10 aggregates + 3 small
    list queries. Stays under 20 even after a populated tenant."""
    with count_queries(engine) as q:
        resp = client.get(
            "/api/v1/finance/reports/dashboard", headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    assert q.count <= 22, (
        f"finance dashboard fired {q.count} queries — N+1 regression?\n"
        f"{q.by_table()}"
    )


def test_marketing_state_query_budget(client, auth_headers, engine):
    """/api/v1/marketing/state hits 11 distinct marketing tables — one
    SELECT each, no cross-row N+1."""
    with count_queries(engine) as q:
        resp = client.get("/api/v1/marketing/state", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    # 11 tables + settings singleton + auth = ~15. Budget 20.
    assert q.count <= 20, (
        f"/marketing/state fired {q.count} queries — N+1 regression?\n"
        f"{q.by_table()}"
    )


def test_webchat_conversations_query_budget(client, auth_headers, engine, db):
    """List conversations for a bot — flat list, no per-row child fetch."""
    from app.models.webchat import Bot
    bot = Bot(
        owner_id=db.scalar(__import__("sqlalchemy").select(__import__("app.models.user", fromlist=["User"]).User.id)),
        name="perf-test-bot",
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)

    with count_queries(engine) as q:
        resp = client.get(
            f"/api/v1/webchat/bots/{bot.id}/conversations",
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    # Auth + bot-exists check + conversation list = 3-5. Budget 10.
    assert q.count <= 10, (
        f"/webchat/.../conversations fired {q.count} queries — N+1?\n"
        f"{q.by_table()}"
    )


def test_jobs_list_query_budget(client, auth_headers, engine):
    """Jobs list reads a flat denormalized ``attempts`` counter — no
    per-row JobAttempt fetch."""
    with count_queries(engine) as q:
        resp = client.get("/api/v1/jobs", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert q.count <= 8, (
        f"/jobs fired {q.count} queries — N+1 regression?\n"
        f"{q.by_table()}"
    )


def test_project_analytics_after_n_plus_one_fix(client, auth_headers, engine, db):
    """Regression test for the project-analytics N+1 fix.

    Before the fix, this endpoint did one SELECT * FROM tasks WHERE
    project_id = ? per project + one SELECT story_points per active
    sprint. With 5 projects and 0 sprints that was 6+ extra queries.
    The bulk-aggregate rewrite collapses those into 2 grouped queries
    regardless of the row count.
    """
    _seed_projects_with_tasks(db, n_projects=5, tasks_each=4)

    with count_queries(engine) as q:
        resp = client.get("/api/v1/projects/analytics", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    # Before fix: ~20+ queries for 5 projects. After fix: < 20 regardless
    # of project count. Budget set to 20 so the test still works on the
    # busy default-tenant dataset other tests leave behind.
    assert q.count <= 20, (
        f"/projects/analytics fired {q.count} queries on 5 projects "
        f"— the bulk-aggregate fix has regressed.\n"
        f"by_table={q.by_table()}"
    )


def test_query_counter_records_statements(engine, db):
    """Unit sanity-check on the QueryCounter itself."""
    with count_queries(engine) as q:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.execute(__import__("sqlalchemy").text("SELECT 2"))
    assert q.count == 2
    assert len(q.statements) == 2
    assert all(s.strip().upper().startswith("SELECT") for s in q.statements)
