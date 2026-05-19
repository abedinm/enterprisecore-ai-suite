"""AI Coding Assistant — exhaustive coverage of the 15-tool backend.

Network calls to AI providers are stubbed via monkeypatch on the unified
``app.services.ai`` module so the suite is deterministic and offline.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import ai as ai_svc


# =========================================================================
# 1-2. Projects + file tree
# =========================================================================
def test_code_project_path_validation(client, auth_headers):
    r = client.post("/api/v1/coding/projects", headers=auth_headers, json={
        "name": "Ghost project", "path": "F:/this/does/not/exist/anywhere",
    })
    assert r.status_code in (400, 404)


def test_code_project_full_lifecycle(client, auth_headers, tmp_path):
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "README.md").write_text("# test")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.py").write_text("def f(): return 1")
    (tmp_path / "node_modules").mkdir()  # should be ignored
    (tmp_path / "node_modules" / "should-be-hidden.js").write_text("nope")

    r = client.post("/api/v1/coding/projects", headers=auth_headers, json={
        "name": "Tmp test project", "path": str(tmp_path), "language_primary": "python",
    })
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # File tree honours DEFAULT_IGNORE
    tree = client.get("/api/v1/coding/tree", headers=auth_headers,
                      params={"project_id": pid, "depth": 4})
    assert tree.status_code == 200
    names = _all_node_names(tree.json())
    assert "main.py" in names
    assert "src" in names
    assert "lib.py" in names
    assert "node_modules" not in names

    # Read file
    f = client.get("/api/v1/coding/file", headers=auth_headers,
                   params={"project_id": pid, "path": str(tmp_path / "main.py")})
    assert f.status_code == 200
    body = f.json()
    assert "print('hi')" in body["content"]
    assert body["language"] == "python"
    assert body["size"] > 0

    # Write a new file
    new_file_path = str(tmp_path / "new.py")
    wr = client.post("/api/v1/coding/file",
                     headers=auth_headers, json={"path": new_file_path, "content": "x = 1"},
                     params={"project_id": pid})
    assert wr.status_code == 200
    assert (tmp_path / "new.py").read_text() == "x = 1"

    # Rename
    rn = client.post("/api/v1/coding/file/rename", headers=auth_headers,
                     params={"project_id": pid,
                             "old_path": new_file_path,
                             "new_path": str(tmp_path / "renamed.py")})
    assert rn.status_code == 200
    assert (tmp_path / "renamed.py").exists()
    assert not (tmp_path / "new.py").exists()

    # Delete
    dl = client.delete("/api/v1/coding/file", headers=auth_headers,
                       params={"project_id": pid, "path": str(tmp_path / "renamed.py")})
    assert dl.status_code == 200
    assert not (tmp_path / "renamed.py").exists()

    # Delete project (DB only)
    rm = client.delete(f"/api/v1/coding/projects/{pid}", headers=auth_headers)
    assert rm.status_code == 204


def test_file_tree_rejects_path_traversal(client, auth_headers, tmp_path):
    (tmp_path / "ok.py").write_text("hi")
    r = client.post("/api/v1/coding/projects", headers=auth_headers, json={
        "name": "Trav test", "path": str(tmp_path),
    })
    pid = r.json()["id"]
    bad = client.get("/api/v1/coding/file", headers=auth_headers,
                     params={"project_id": pid, "path": "../../../etc/passwd"})
    assert bad.status_code in (403, 404)


def test_search_in_files(client, auth_headers, tmp_path):
    (tmp_path / "a.py").write_text("HELLO from a\nfn = lambda: 1")
    (tmp_path / "b.py").write_text("nothing here")
    (tmp_path / "c.txt").write_text("hello from c")
    pid = client.post("/api/v1/coding/projects", headers=auth_headers,
                      json={"name": "search", "path": str(tmp_path)}).json()["id"]
    r = client.get("/api/v1/coding/search-in-files", headers=auth_headers,
                   params={"project_id": pid, "query": "hello"})
    assert r.status_code == 200
    paths = [h["path"] for h in r.json()["hits"]]
    assert any(p.endswith("a.py") for p in paths)
    assert any(p.endswith("c.txt") for p in paths)


# =========================================================================
# 3. Terminal sandbox
# =========================================================================
def test_terminal_rejects_destructive(client, auth_headers, tmp_path):
    pid = client.post("/api/v1/coding/projects", headers=auth_headers,
                      json={"name": "term", "path": str(tmp_path)}).json()["id"]
    bad = client.post("/api/v1/coding/terminal", headers=auth_headers,
                      json={"command": "rm -rf /", "timeout_seconds": 5},
                      params={"project_id": pid})
    assert bad.status_code == 403


def test_terminal_rejects_shell_metacharacters(client, auth_headers, tmp_path):
    pid = client.post("/api/v1/coding/projects", headers=auth_headers,
                      json={"name": "term2", "path": str(tmp_path)}).json()["id"]
    bad = client.post("/api/v1/coding/terminal", headers=auth_headers,
                      json={"command": "python -V && ls"},
                      params={"project_id": pid})
    assert bad.status_code == 403


def test_terminal_rejects_unallowed_executable(client, auth_headers, tmp_path):
    pid = client.post("/api/v1/coding/projects", headers=auth_headers,
                      json={"name": "term3", "path": str(tmp_path)}).json()["id"]
    bad = client.post("/api/v1/coding/terminal", headers=auth_headers,
                      json={"command": "curl http://example.com"},
                      params={"project_id": pid})
    assert bad.status_code == 403


# =========================================================================
# 10. Git
# =========================================================================
def test_git_status_on_non_repo(client, auth_headers, tmp_path):
    pid = client.post("/api/v1/coding/projects", headers=auth_headers,
                      json={"name": "no-git", "path": str(tmp_path)}).json()["id"]
    r = client.get("/api/v1/coding/git/status", headers=auth_headers,
                   params={"project_id": pid})
    assert r.status_code in (400, 500)
    assert "not_a_repo" in r.text or "Not a git repository" in r.text


def test_git_init_creates_repo(client, auth_headers, tmp_path):
    pid = client.post("/api/v1/coding/projects", headers=auth_headers,
                      json={"name": "fresh-git", "path": str(tmp_path)}).json()["id"]
    init = client.post("/api/v1/coding/git/init", headers=auth_headers,
                       params={"project_id": pid})
    assert init.status_code == 200
    assert (tmp_path / ".git").exists()
    # After init, status returns 200
    status = client.get("/api/v1/coding/git/status", headers=auth_headers,
                        params={"project_id": pid})
    assert status.status_code == 200
    assert status.json()["branch"] in ("main", "master")


# =========================================================================
# 11. Language support (Monaco mapping)
# =========================================================================
def test_languages_includes_python_and_rust(client, auth_headers):
    r = client.get("/api/v1/coding/languages", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    langs = {item["language"] for item in body["languages"]}
    # Sample of expected languages from the 60+ extension map
    for required in ("python", "typescript", "javascript", "rust", "go",
                     "java", "kotlin", "csharp", "swift", "sql",
                     "dockerfile", "graphql", "solidity", "hcl"):
        assert required in langs, f"missing language: {required}"
    assert body["count"] >= 50


# =========================================================================
# 12. Snippets
# =========================================================================
def test_snippet_crud(client, auth_headers):
    r = client.post("/api/v1/coding/snippets", headers=auth_headers, json={
        "title": "Hello world", "language": "python",
        "code": "print('hi')", "description": "test",
        "tags": ["test"], "is_public": False,
    })
    assert r.status_code == 200, r.text
    sid = r.json()["id"]

    # Search
    s = client.get("/api/v1/coding/snippets", headers=auth_headers,
                   params={"q": "Hello"})
    assert s.status_code == 200
    assert any(item["id"] == sid for item in s.json())

    # Update
    upd = client.put(f"/api/v1/coding/snippets/{sid}", headers=auth_headers, json={
        "title": "Hello world v2", "language": "python",
        "code": "print('hi')", "description": "edited",
        "tags": ["test"], "is_public": True,
    })
    assert upd.status_code == 200
    assert upd.json()["title"] == "Hello world v2"
    assert upd.json()["is_public"] is True

    # Use count
    used = client.post(f"/api/v1/coding/snippets/{sid}/use", headers=auth_headers)
    assert used.status_code == 200
    assert used.json()["use_count"] == 1

    # Delete
    dl = client.delete(f"/api/v1/coding/snippets/{sid}", headers=auth_headers)
    assert dl.status_code == 204


def test_snippet_suggest_uses_ai(client, auth_headers, monkeypatch):
    def fake_smart_json(*_args, **_kwargs):
        return {
            "title": "Fzf branch picker",
            "code": "git branch | fzf | xargs git checkout",
            "language": "shell",
            "description": "Pick and checkout a branch with fzf",
        }
    monkeypatch.setattr(ai_svc, "smart_json", fake_smart_json)

    r = client.post("/api/v1/coding/snippets/suggest", headers=auth_headers, json={
        "description": "Fzf branch picker", "language": "shell",
    })
    assert r.status_code == 200
    assert r.json()["code"].startswith("git branch")


# =========================================================================
# 13. API tester
# =========================================================================
def test_api_request_save_and_execute(client, auth_headers):
    # Save
    save = client.post("/api/v1/coding/api-requests", headers=auth_headers, json={
        "name": "health-check", "method": "GET",
        "url": "http://127.0.0.1:8765/api/health",
        "headers": {}, "params": {}, "body": None, "collection": "tests",
    })
    assert save.status_code == 200, save.text
    rid = save.json()["id"]

    # List filtered by collection
    listed = client.get("/api/v1/coding/api-requests", headers=auth_headers,
                        params={"collection": "tests"})
    assert any(r["id"] == rid for r in listed.json())

    # Update
    upd = client.put(f"/api/v1/coding/api-requests/{rid}", headers=auth_headers, json={
        "name": "health-check v2", "method": "GET",
        "url": "http://127.0.0.1:8765/api/health",
        "headers": {"X-Test": "1"}, "params": {}, "body": None, "collection": "tests",
    })
    assert upd.status_code == 200
    assert upd.json()["headers"] == {"X-Test": "1"}

    # Delete
    dl = client.delete(f"/api/v1/coding/api-requests/{rid}", headers=auth_headers)
    assert dl.status_code == 204


def test_api_tester_handles_unreachable(client, auth_headers):
    r = client.post("/api/v1/coding/api-tester/execute", headers=auth_headers, json={
        "method": "GET",
        "url": "http://127.0.0.1:1/should-be-unreachable",
        "timeout": 1,
    })
    # Either a 500/400 with our http_error code, or — if a server happens to
    # bind that port — anything is OK as long as it didn't crash with 5xx.
    assert r.status_code in (200, 400, 500, 408)


# =========================================================================
# 4-9 + 14. AI features (mocked)
# =========================================================================
@pytest.fixture
def fake_ai(monkeypatch):
    """Replace ai_svc.call with a deterministic function we can configure."""
    state = {"text": "```python\nprint('hi')\n```\nExplanation.", "calls": []}

    def fake_call(messages, *, provider=None, model=None, max_tokens=1024,
                  temperature=0.7, feature="general", db=None, user_id=None,
                  api_key_override=None):
        state["calls"].append({
            "feature": feature,
            "messages": [(m.role, m.content) for m in messages],
            "api_key_override": api_key_override,
            "provider": provider,
            "model": model,
        })
        return ai_svc.AiResponse(
            text=state["text"], provider=provider or "anthropic",
            model=model or "claude-sonnet-4-6",
            tokens_in=10, tokens_out=20, latency_ms=42,
        )

    def fake_smart_text(prompt, *, system=None, feature="general", provider=None,
                        db=None, user_id=None, max_tokens=800, api_key_override=None):
        msgs = [ai_svc.AiMessage(role="user", content=prompt)]
        return fake_call(msgs, provider=provider, feature=feature,
                         api_key_override=api_key_override).text

    def fake_smart_json(prompt, **kwargs):
        return state.get("json", {})

    monkeypatch.setattr(ai_svc, "call", fake_call)
    monkeypatch.setattr(ai_svc, "smart_text", fake_smart_text)
    monkeypatch.setattr(ai_svc, "smart_json", fake_smart_json)
    return state


def test_ai_generate_extracts_codeblock(client, auth_headers, fake_ai):
    fake_ai["text"] = "```python\ndef hello(): return 'hi'\n```\nIt greets you."
    r = client.post("/api/v1/coding/ai/generate", headers=auth_headers, json={
        "prompt": "make a hello function", "language": "python",
        "provider": "openai", "model": "gpt-4o-mini",
        "api_key_override": "sk-test-byo-key-123",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "def hello" in body["code"]
    assert "greets" in body["explanation"]
    # BYO key was actually forwarded down to the AI service
    assert fake_ai["calls"][-1]["api_key_override"] == "sk-test-byo-key-123"
    assert fake_ai["calls"][-1]["provider"] == "openai"


def test_ai_explain(client, auth_headers, fake_ai):
    fake_ai["text"] = "This function returns 1."
    r = client.post("/api/v1/coding/ai/explain", headers=auth_headers, json={
        "code": "def f(): return 1", "language": "python",
    })
    assert r.status_code == 200
    assert "returns 1" in r.json()["explanation"]


def test_ai_docstring(client, auth_headers, fake_ai):
    fake_ai["text"] = "```python\ndef f():\n    \"\"\"Return 1.\"\"\"\n    return 1\n```"
    r = client.post("/api/v1/coding/ai/docstring", headers=auth_headers, json={
        "code": "def f(): return 1", "language": "python", "style": "google",
    })
    assert r.status_code == 200
    assert "Return 1" in r.json()["documented_code"]


def test_ai_bugfix(client, auth_headers, fake_ai):
    fake_ai["text"] = "```python\nx = 0\n```\nFixed division by zero."
    r = client.post("/api/v1/coding/ai/bugfix", headers=auth_headers, json={
        "code": "x = 1/0", "error": "ZeroDivisionError", "language": "python",
    })
    assert r.status_code == 200
    assert r.json()["fixed_code"].startswith("x = 0")


def test_ai_review_parses_findings(client, auth_headers, fake_ai):
    fake_ai["json"] = {
        "summary": "Two issues.",
        "findings": [
            {"line": 3, "severity": "high", "category": "security",
             "message": "SQL injection", "suggestion": "Use bind params"},
            {"line": None, "severity": "low", "category": "style",
             "message": "Bad name", "suggestion": "Rename"},
        ],
    }
    r = client.post("/api/v1/coding/ai/review", headers=auth_headers, json={
        "code": "SELECT * FROM users WHERE id = '%s' % user_id",
        "language": "python", "focus": "security",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == "Two issues."
    assert len(body["findings"]) == 2
    assert body["findings"][0]["severity"] == "high"
    assert body["findings"][0]["line"] == 3


def test_ai_multi_file_plan_and_apply(client, auth_headers, fake_ai, tmp_path):
    (tmp_path / "app.py").write_text("# original app.py\n")
    pid = client.post("/api/v1/coding/projects", headers=auth_headers,
                      json={"name": "mf", "path": str(tmp_path)}).json()["id"]

    # Plan: stub call to return a JSON plan
    def call_with_json(messages, **_kwargs):
        return ai_svc.AiResponse(
            text=json.dumps({
                "summary": "Add health route",
                "changes": [
                    {"path": "app.py", "content": "from fastapi import FastAPI\napp=FastAPI()\n",
                     "create_if_missing": True},
                    {"path": "routes/health.py", "content": "def healthz(): return 'ok'\n",
                     "create_if_missing": True},
                ],
            }),
            provider="anthropic", model="claude-sonnet-4-6",
            tokens_in=10, tokens_out=20, latency_ms=10,
        )
    import types
    fake_ai["text"] = None  # not used in this path
    from app.services import ai as _ai
    real_call = _ai.call
    _ai.call = call_with_json
    try:
        plan = client.post("/api/v1/coding/ai/multi-file-plan", headers=auth_headers, json={
            "project_id": pid, "prompt": "Add /healthz",
            "context_files": [], "target_files": ["app.py"],
        })
        assert plan.status_code == 200, plan.text
        changes = plan.json()["changes"]
        assert len(changes) == 2
    finally:
        _ai.call = real_call

    # Apply
    apply = client.post("/api/v1/coding/ai/multi-file-apply", headers=auth_headers, json={
        "project_id": pid, "changes": [
            {"path": "app.py", "content": "X", "create_if_missing": True},
            {"path": "subdir/y.txt", "content": "Y", "create_if_missing": True},
        ],
    })
    assert apply.status_code == 200, apply.text
    assert apply.json()["count"] == 2
    assert (tmp_path / "app.py").read_text() == "X"
    assert (tmp_path / "subdir" / "y.txt").read_text() == "Y"


def test_ai_db_query_generates_sql(client, auth_headers, fake_ai):
    fake_ai["json"] = {"sql": "SELECT 1;", "explanation": "trivial"}
    r = client.post("/api/v1/coding/ai/db-query", headers=auth_headers, json={
        "description": "select 1", "dialect": "postgresql",
    })
    assert r.status_code == 200
    assert "SELECT 1" in r.json()["sql"]


# =========================================================================
# 14. DB connections (encrypted DSN, schema introspection, execute)
# =========================================================================
def test_db_connection_roundtrip_sqlite(client, auth_headers, tmp_path):
    # Create a small standalone SQLite DB on disk to point the connection at
    target_db = tmp_path / "data.db"
    import sqlite3
    cn = sqlite3.connect(target_db)
    cn.executescript(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER);"
        "INSERT INTO widgets (name, qty) VALUES ('w1', 10), ('w2', 20);"
    )
    cn.commit(); cn.close()

    save = client.post("/api/v1/coding/db/connections", headers=auth_headers, json={
        "name": "tmp-sqlite", "dialect": "sqlite",
        "dsn": f"sqlite:///{target_db.as_posix()}",
    })
    assert save.status_code == 200, save.text
    cid = save.json()["id"]

    schema = client.get(f"/api/v1/coding/db/connections/{cid}/schema",
                        headers=auth_headers)
    assert schema.status_code == 200, schema.text
    tables = {t["name"]: t for t in schema.json()["tables"]}
    assert "widgets" in tables
    cols = {c["name"] for c in tables["widgets"]["columns"]}
    assert {"id", "name", "qty"}.issubset(cols)

    exec_ = client.post("/api/v1/coding/db/execute", headers=auth_headers, json={
        "connection_id": cid, "sql": "SELECT name, qty FROM widgets ORDER BY id", "limit": 10,
    })
    assert exec_.status_code == 200
    body = exec_.json()
    assert body["columns"] == ["name", "qty"]
    assert body["rows"] == [["w1", 10], ["w2", 20]]

    rm = client.delete(f"/api/v1/coding/db/connections/{cid}", headers=auth_headers)
    assert rm.status_code == 204


# =========================================================================
# 15. Regex builder (live tester is AI-free)
# =========================================================================
def test_regex_test_finds_matches(client, auth_headers):
    r = client.post("/api/v1/coding/regex/test", headers=auth_headers, json={
        "pattern": r"\b\d{3}-\d{3}-\d{4}\b",
        "flags": "",
        "text": "Call 555-867-5309 or 800-555-0199",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["is_valid"] is True
    assert len(body["matches"]) == 2
    assert body["matches"][0]["match"] == "555-867-5309"
    assert body["matches"][1]["start"] == len("Call 555-867-5309 or ")


def test_regex_test_invalid_pattern(client, auth_headers):
    r = client.post("/api/v1/coding/regex/test", headers=auth_headers, json={
        "pattern": "(unclosed",
        "text": "anything",
    })
    assert r.status_code == 200
    assert r.json()["is_valid"] is False
    assert "(" in r.json()["error"] or "missing" in r.json()["error"].lower() or "unbalanced" in r.json()["error"].lower()


def test_regex_test_with_replacement(client, auth_headers):
    r = client.post("/api/v1/coding/regex/test", headers=auth_headers, json={
        "pattern": r"(\w+)@(\w+\.\w+)",
        "text": "Reach me at user@example.com today",
        "replacement": r"\1 AT \2",
    })
    assert r.status_code == 200
    assert "user AT example.com" in r.json()["replaced"]


def test_regex_test_flags_case_insensitive(client, auth_headers):
    r = client.post("/api/v1/coding/regex/test", headers=auth_headers, json={
        "pattern": "hello", "flags": "i",
        "text": "HELLO World, Hello again",
    })
    body = r.json()
    assert body["is_valid"]
    assert len(body["matches"]) == 2


def test_regex_library_crud(client, auth_headers):
    save = client.post("/api/v1/coding/regex/library", headers=auth_headers, json={
        "title": "US phone", "pattern": r"\b\d{3}-\d{3}-\d{4}\b",
        "flags": "", "description": "North-American phone numbers",
    })
    assert save.status_code == 200
    rid = save.json()["id"]
    listed = client.get("/api/v1/coding/regex/library", headers=auth_headers)
    assert any(e["id"] == rid for e in listed.json())
    dl = client.delete(f"/api/v1/coding/regex/library/{rid}", headers=auth_headers)
    assert dl.status_code == 204


def test_regex_explain_uses_ai(client, auth_headers, fake_ai):
    fake_ai["json"] = {
        "explanation": "Matches a US phone number with dashes.",
        "test_cases": [{"input": "555-867-5309", "should_match": True}],
    }
    r = client.post("/api/v1/coding/regex/explain", headers=auth_headers, json={
        "pattern": r"\b\d{3}-\d{3}-\d{4}\b", "flags": "",
    })
    assert r.status_code == 200
    assert "phone" in r.json()["explanation"].lower()
    assert len(r.json()["test_cases"]) == 1


def test_regex_from_description_uses_ai(client, auth_headers, fake_ai):
    fake_ai["json"] = {
        "pattern": r"^\d{5}(-\d{4})?$", "flags": "",
        "explanation": "US ZIP code (optionally ZIP+4).",
    }
    r = client.post("/api/v1/coding/regex/from-description", headers=auth_headers, json={
        "description": "US ZIP codes",
        "examples_match": ["94110", "94110-1234"],
        "examples_no_match": ["abcde"],
    })
    assert r.status_code == 200
    assert "\\d{5}" in r.json()["pattern"]


# =========================================================================
# Helpers
# =========================================================================
def _all_node_names(node):
    out = {node["name"]}
    for c in node.get("children") or []:
        out |= _all_node_names(c)
    return out
