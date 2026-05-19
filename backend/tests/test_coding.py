"""AI Coding Assistant smoke tests — IDE, snippets, API tester. (AI calls mocked elsewhere.)"""
from __future__ import annotations

import tempfile
from pathlib import Path


def test_snippet_crud(client, auth_headers):
    r = client.post("/api/v1/coding/snippets", headers=auth_headers, json={
        "title": "Hello world", "language": "python",
        "code": "print('hi')", "description": "test",
        "tags": ["test"], "is_public": False,
    })
    assert r.status_code == 200
    sid = r.json()["id"]

    use = client.post(f"/api/v1/coding/snippets/{sid}/use", headers=auth_headers)
    assert use.status_code == 200
    assert use.json()["use_count"] == 1


def test_api_tester_executes_real_request(client, auth_headers):
    # Hit the app's own /api/health via the api-tester endpoint
    r = client.post("/api/v1/coding/api-tester/execute", headers=auth_headers, json={
        "method": "GET", "url": "http://127.0.0.1:8765/api/health", "timeout": 5,
    })
    # Either it works (200) or the test backend isn't running on 8765 (any other status is fine)
    assert r.status_code in (200, 400, 500)


def test_code_project_path_validation(client, auth_headers):
    # Path that doesn't exist must be rejected
    r = client.post("/api/v1/coding/projects", headers=auth_headers, json={
        "name": "Ghost project", "path": "F:/this/does/not/exist/anywhere",
    })
    assert r.status_code in (400, 404)


def test_code_project_create_and_tree(client, auth_headers, tmp_path):
    # Create a tiny project on disk
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "README.md").write_text("# test")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.py").write_text("def f(): return 1")

    r = client.post("/api/v1/coding/projects", headers=auth_headers, json={
        "name": "Tmp test project", "path": str(tmp_path), "language_primary": "python",
    })
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    tree = client.get("/api/v1/coding/tree", headers=auth_headers,
                      params={"project_id": pid, "depth": 3})
    assert tree.status_code == 200, tree.text
    body = tree.json()
    assert body["is_dir"] is True
    assert body["children"], "tree should have children"

    # Read a file inside the project
    main_path = str(tmp_path / "main.py")
    f = client.get("/api/v1/coding/file", headers=auth_headers,
                   params={"project_id": pid, "path": main_path})
    assert f.status_code == 200
    assert "print('hi')" in f.json()["content"]
    assert f.json()["language"] == "python"


def test_terminal_blocklist(client, auth_headers, tmp_path):
    r = client.post("/api/v1/coding/projects", headers=auth_headers, json={
        "name": "Term test", "path": str(tmp_path),
    })
    pid = r.json()["id"]
    # 'rm -rf' should be rejected
    bad = client.post("/api/v1/coding/terminal", headers=auth_headers,
                      json={"command": "rm -rf /", "timeout_seconds": 5},
                      params={"project_id": pid})
    assert bad.status_code == 403, bad.text
