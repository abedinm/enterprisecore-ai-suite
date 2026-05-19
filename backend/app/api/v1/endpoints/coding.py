"""AI Coding Assistant — full backend for the 15-tool IDE module."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppError, NotFoundError
from app.core.security import decrypt_text, encrypt_text
from app.db.session import get_db
from app.models.coding import (
    ApiRequest, CodeProject, CodeSnippet, DatabaseConnection, GitRepo,
    RegexLibraryEntry,
)
from app.models.user import User, UserRole
from app.schemas.coding import (
    ApiExecIn, ApiExecOut, ApiRequestIn, ApiRequestOut, BugFixIn, BugFixOut,
    CodeGenIn, CodeGenOut, CodeProjectIn, CodeProjectOut, CodeReviewFinding,
    CodeReviewIn, CodeReviewOut, CodeSnippetIn, CodeSnippetOut, CodingChatIn,
    CodingChatOut, DBConnectionIn, DBConnectionOut, DBExecuteIn, DBExecuteOut,
    DBQueryIn, DBQueryOut, DBSchemaOut, DBSchemaTable, DocstringIn, DocstringOut,
    ExplainCodeIn, ExplainCodeOut, FileContent, FileNode, FilePatchOp,
    FileSaveIn, GitCommitIn, GitCommitOut, GitRemoteAction, GitStatusOut,
    MultiFileApplyIn, MultiFileEditIn, MultiFileEditOut, RegexExplainBuilderIn,
    RegexExplainBuilderOut, RegexFromDescriptionIn, RegexFromDescriptionOut,
    RegexLibraryIn, RegexLibraryOut, RegexMatch, RegexTestIn, RegexTestOut,
    SnippetSuggestIn, SnippetSuggestOut, TerminalCommandIn, TerminalCommandOut,
)
from app.services import ai as ai_svc

router = APIRouter()

# ---- Constants ----------------------------------------------------------
LANGUAGE_BY_EXT = {
    ".py": "python", ".pyw": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".cr": "crystal",
    ".cs": "csharp", ".fs": "fsharp", ".vb": "vb",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c": "c",
    ".h": "cpp", ".hpp": "cpp", ".hxx": "cpp",
    ".m": "objective-c", ".mm": "objective-c",
    ".swift": "swift", ".php": "php", ".pl": "perl", ".pm": "perl",
    ".lua": "lua", ".r": "r", ".R": "r", ".jl": "julia", ".dart": "dart",
    ".html": "html", ".htm": "html", ".xhtml": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".json": "json", ".jsonc": "jsonc", ".yaml": "yaml", ".yml": "yaml",
    ".md": "markdown", ".markdown": "markdown", ".mdx": "markdown",
    ".rst": "restructuredtext", ".tex": "latex",
    ".sql": "sql", ".psql": "sql", ".mysql": "sql",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".fish": "shell",
    ".ps1": "powershell", ".psm1": "powershell", ".bat": "bat", ".cmd": "bat",
    ".vue": "vue", ".svelte": "svelte", ".astro": "astro",
    ".xml": "xml", ".plist": "xml", ".svg": "xml",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".dockerfile": "dockerfile", ".containerfile": "dockerfile",
    ".tf": "hcl", ".tfvars": "hcl",
    ".graphql": "graphql", ".gql": "graphql",
    ".proto": "protobuf", ".thrift": "thrift",
    ".ex": "elixir", ".exs": "elixir", ".erl": "erlang",
    ".hs": "haskell", ".clj": "clojure", ".elm": "elm",
    ".nim": "nim", ".zig": "zig", ".v": "v",
    ".sol": "solidity", ".vy": "vyper",
    ".asm": "asm", ".s": "asm",
}

DEFAULT_IGNORE = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
                  "dist", "build", ".idea", ".vscode", ".next", ".nuxt", "out",
                  ".turbo", "coverage", ".mypy_cache", ".ruff_cache", ".cache",
                  ".tox", ".gradle", "target", "bin", "obj"}

TERMINAL_BLOCKLIST = {"rm", "del", "format", "mkfs", "dd", "shutdown", "reboot",
                      "poweroff", "halt", "fdisk", "deluser", "userdel"}

# Allowlist of executables the sandboxed terminal will run. Anything else is
# rejected. Tightening this is safer than a blocklist (which is bypassable via
# new commands, PATH tricks, aliases, etc.).
TERMINAL_ALLOWLIST = {
    # Python / Node / package managers
    "python", "python3", "pip", "pip3", "pipx", "uv", "poetry",
    "node", "npm", "npx", "yarn", "pnpm", "bun",
    # Version control
    "git",
    # Containers / build
    "make", "cargo", "go", "mvn", "gradle", "dotnet", "rake",
    # Inspection (read-only / harmless)
    "ls", "dir", "pwd", "cat", "type", "head", "tail", "wc", "find", "where",
    "grep", "rg", "ack", "ag", "tree", "stat", "du", "df", "file",
    "echo", "printf",
    # Test runners
    "pytest", "tox", "jest", "vitest", "mocha", "phpunit",
    # Lint / format
    "ruff", "black", "isort", "mypy", "pylint", "flake8", "eslint", "prettier",
    "tsc", "rustfmt", "gofmt",
}

# Shell metachars that allow command chaining / redirection / substitution.
# Even when shell=False is used, presence of these in the raw command means
# the user is trying to use shell features that the sandboxed runner does NOT
# expand — silently dropping them would be surprising. We reject upfront.
SHELL_METACHAR_RE = re.compile(r"[;&|`$<>\n\r]|>>|\$\(|\$\{|`")


# ---- Helpers ------------------------------------------------------------
def _resolve_project_path(db: Session, project_id: str | None, path: str | None) -> Path:
    """Resolve a request path inside a project's tree; prevent traversal."""
    if not project_id and not path:
        raise AppError("project_id or absolute path required", code="bad_request")
    if project_id:
        proj = db.get(CodeProject, project_id)
        if not proj:
            raise NotFoundError("Code project not found")
        root = Path(proj.path).expanduser().resolve()
        if path:
            candidate = (root / path.lstrip("/\\")).resolve() if not Path(path).is_absolute() \
                else Path(path).expanduser().resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                raise AppError("Path is outside project root",
                              code="path_traversal", status_code=403) from None
            return candidate
        return root
    return Path(path).expanduser().resolve()


def _read_text_safe(p: Path, limit_bytes: int = 4_000_000) -> str:
    if p.stat().st_size > limit_bytes:
        raise AppError(f"File too large ({p.stat().st_size} bytes; limit {limit_bytes})",
                      code="too_large")
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_bytes().decode("utf-8", errors="replace")


def _detect_language(p: Path) -> str | None:
    if p.name.lower() in {"dockerfile", "containerfile"}:
        return "dockerfile"
    if p.name.lower() == "makefile":
        return "makefile"
    return LANGUAGE_BY_EXT.get(p.suffix.lower())


def _strip_code_block(text: str) -> str:
    """Strip a single leading/trailing ```lang fence (and language tag) if present."""
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline >= 0:
            t = t[first_newline + 1:]
        else:
            t = t.lstrip("`")
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    return t


def _extract_first_codeblock(text: str) -> tuple[str, str]:
    """Return (code, surrounding_explanation) for the first fenced block in `text`."""
    m = re.search(r"```([\w+-]*)\n(.*?)```", text, re.DOTALL)
    if not m:
        return text.strip(), ""
    code = m.group(2).rstrip()
    explanation = (text[:m.start()] + text[m.end():]).strip()
    return code, explanation


def _build_context_block(db: Session, project_id: str | None,
                         files: list[str], limit_per_file: int = 30_000) -> str:
    if not project_id or not files:
        return ""
    chunks = []
    for f in files[:8]:
        try:
            p = _resolve_project_path(db, project_id, f)
            if p.exists() and p.is_file():
                lang = _detect_language(p) or ""
                chunks.append(f"\n\n### {f}\n```{lang}\n{_read_text_safe(p, limit_per_file)}\n```")
        except Exception:
            continue
    return "".join(chunks)


# ---- 1-2. Projects + File tree -----------------------------------------
@router.get("/projects", response_model=list[CodeProjectOut])
def list_code_projects(db: Session = Depends(get_db),
                       _: User = Depends(get_current_user)):
    return db.scalars(select(CodeProject).order_by(CodeProject.created_at.desc())).all()


@router.post("/projects", response_model=CodeProjectOut)
def create_code_project(payload: CodeProjectIn, db: Session = Depends(get_db),
                        current: User = Depends(get_current_user)):
    root = Path(payload.path).expanduser().resolve()
    if not root.exists():
        raise AppError(f"Path does not exist: {root}", code="path_not_found")
    if not root.is_dir():
        raise AppError(f"Path is not a directory: {root}", code="not_a_directory")
    proj = CodeProject(
        name=payload.name, path=str(root), description=payload.description,
        language_primary=payload.language_primary, owner_id=current.id,
        is_git=(root / ".git").exists(),
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@router.delete("/projects/{pid}", status_code=204)
def delete_code_project(pid: str, db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)):
    proj = db.get(CodeProject, pid)
    if proj:
        db.delete(proj)
        db.commit()


@router.get("/tree", response_model=FileNode)
def file_tree(project_id: str, path: str | None = None, depth: int = 3,
              db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    root = _resolve_project_path(db, project_id, path)
    if not root.exists():
        raise NotFoundError("Path not found")
    depth = max(1, min(depth, 6))

    def _build(p: Path, remaining: int) -> FileNode:
        node = FileNode(
            name=p.name or str(p),
            path=str(p),
            is_dir=p.is_dir(),
            size=p.stat().st_size if p.is_file() else None,
        )
        if p.is_dir() and remaining > 0:
            children: list[FileNode] = []
            try:
                for child in sorted(p.iterdir(),
                                    key=lambda x: (not x.is_dir(), x.name.lower())):
                    if child.name in DEFAULT_IGNORE:
                        continue
                    children.append(_build(child, remaining - 1))
            except PermissionError:
                pass
            node.children = children
        return node

    return _build(root, depth)


@router.get("/file", response_model=FileContent)
def read_file(project_id: str, path: str, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    p = _resolve_project_path(db, project_id, path)
    if not p.exists() or not p.is_file():
        raise NotFoundError("File not found")
    return FileContent(
        path=str(p), content=_read_text_safe(p),
        language=_detect_language(p), size=p.stat().st_size,
    )


@router.post("/file")
def save_file(payload: FileSaveIn, project_id: str, db: Session = Depends(get_db),
              _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    p = _resolve_project_path(db, project_id, payload.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload.content, encoding="utf-8")
    return {"path": str(p), "size": p.stat().st_size}


@router.delete("/file")
def delete_file(project_id: str, path: str, db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.developer, UserRole.admin))):
    p = _resolve_project_path(db, project_id, path)
    if not p.exists():
        raise NotFoundError("File not found")
    if p.is_dir():
        import shutil
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"deleted": str(p)}


@router.post("/file/new")
def create_file(project_id: str, path: str, is_dir: bool = False,
                db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    p = _resolve_project_path(db, project_id, path)
    if p.exists():
        raise AppError("Path already exists", code="exists", status_code=409)
    if is_dir:
        p.mkdir(parents=True, exist_ok=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    return {"path": str(p), "is_dir": is_dir}


@router.post("/file/rename")
def rename_file(project_id: str, old_path: str, new_path: str,
                db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    src = _resolve_project_path(db, project_id, old_path)
    dst = _resolve_project_path(db, project_id, new_path)
    if not src.exists():
        raise NotFoundError("Source not found")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return {"old": str(src), "new": str(dst)}


@router.get("/search-in-files")
def search_in_files(project_id: str, query: str, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    """Grep-style search inside the project."""
    if len(query) < 2:
        raise AppError("Query must be at least 2 characters", code="bad_request")
    root = _resolve_project_path(db, project_id, None)
    hits: list[dict] = []
    pat = re.compile(re.escape(query), re.IGNORECASE)
    skip_exts = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz",
                 ".exe", ".dll", ".so", ".bin", ".woff", ".woff2", ".ttf"}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in DEFAULT_IGNORE for part in p.parts):
            continue
        if p.suffix.lower() in skip_exts:
            continue
        if p.stat().st_size > 500_000:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if pat.search(line):
                hits.append({"path": str(p.relative_to(root)), "line": i,
                             "snippet": line.strip()[:300]})
                if len(hits) >= 300:
                    return {"query": query, "hits": hits, "truncated": True}
    return {"query": query, "hits": hits, "truncated": False}


# ---- 3. Terminal --------------------------------------------------------
def _safe_argv(raw_command: str) -> list[str]:
    """Parse a shell-style command into argv WITHOUT enabling shell expansion.

    Raises AppError if:
      * the input is empty
      * shell metacharacters are present (chaining, redirection, substitution)
      * the executable isn't in the allowlist
      * the first token resolves to a known-destructive command
    """
    cmd = raw_command.strip()
    if not cmd:
        raise AppError("Empty command", code="empty_command")
    if SHELL_METACHAR_RE.search(cmd):
        raise AppError(
            "Shell metacharacters (& | ; > < ` $() newlines) are not allowed. "
            "Run one command at a time.",
            code="shell_metachar", status_code=403,
        )
    try:
        argv = shlex.split(cmd, posix=False)
    except ValueError as e:
        raise AppError(f"Could not parse command: {e}", code="parse_error") from e
    if not argv:
        raise AppError("Empty command", code="empty_command")
    # Strip quoting helpers shlex may leave behind on Windows-style input
    exe_token = argv[0].strip('"\'')
    base = Path(exe_token).name.lower()
    # Drop extension, e.g. python.exe → python
    base_no_ext = base.rsplit(".", 1)[0] if "." in base else base
    if base_no_ext in TERMINAL_BLOCKLIST:
        raise AppError(f"Destructive command '{base_no_ext}' is blocked",
                      code="command_blocked", status_code=403)
    if base_no_ext not in TERMINAL_ALLOWLIST:
        raise AppError(
            f"Command '{base_no_ext}' is not on the sandbox allowlist. "
            f"Allowed: {', '.join(sorted(TERMINAL_ALLOWLIST))}",
            code="command_not_allowed", status_code=403,
        )
    argv[0] = exe_token
    return argv


def _safe_cwd(db: Session, project_id: str | None, cwd_in: str | None) -> Path | None:
    """Resolve a working directory inside a project root, following symlinks.

    Returns None if no project_id was given (caller must have one for terminal).
    Raises AppError if the resolved path escapes the project root.
    """
    if not project_id:
        return None
    proj = db.get(CodeProject, project_id)
    if not proj:
        raise NotFoundError("Code project not found")
    root = Path(proj.path).expanduser().resolve()
    if cwd_in:
        candidate = (root / cwd_in.lstrip("/\\")).resolve() if not Path(cwd_in).is_absolute() \
            else Path(cwd_in).expanduser().resolve()
    else:
        candidate = root
    try:
        candidate.relative_to(root)
    except ValueError:
        raise AppError("Working directory is outside the project root",
                      code="path_traversal", status_code=403) from None
    if not candidate.is_dir():
        raise NotFoundError("Working directory not found")
    return candidate


def _restricted_env() -> dict[str, str]:
    """Pass through only the env vars a developer-tool process needs.
    Strips API keys, secrets, and the user's shell-modified PATH overrides."""
    import os as _os
    keep = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
            "USERPROFILE", "HOME", "LANG", "LC_ALL", "LC_CTYPE",
            "PYTHONIOENCODING", "PYTHONUNBUFFERED"}
    return {k: v for k, v in _os.environ.items() if k in keep}


@router.post("/terminal", response_model=TerminalCommandOut)
def run_command(payload: TerminalCommandIn, project_id: str | None = None,
                db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.developer, UserRole.admin))):
    """Run ONE allow-listed command, no shell, sandboxed to the project root.

    The sandbox refuses:
      * commands containing shell metacharacters (`&& || ; | > < $() backticks`)
      * commands whose argv[0] is destructive (rm, del, mkfs, …)
      * commands whose argv[0] is not in TERMINAL_ALLOWLIST
      * working directories that resolve outside the project's root after
        following symlinks
    """
    argv = _safe_argv(payload.command)
    cwd = _safe_cwd(db, project_id, payload.cwd)
    started = time.time()
    try:
        result = subprocess.run(
            argv,
            shell=False,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=max(1, min(payload.timeout_seconds, 180)),
            env=_restricted_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise AppError("Command timed out", code="timeout", status_code=408) from None
    except FileNotFoundError as e:
        raise AppError(f"Executable not found: {e.filename or argv[0]}",
                      code="exe_not_found", status_code=404) from e
    duration_ms = int((time.time() - started) * 1000)
    return TerminalCommandOut(
        stdout=result.stdout[-60_000:],
        stderr=result.stderr[-20_000:],
        exit_code=result.returncode,
        duration_ms=duration_ms,
    )


# ---- 10. Git integration ------------------------------------------------
def _get_repo(db: Session, project_id: str):
    try:
        from git import Repo
    except ImportError:
        raise AppError("GitPython is not installed", code="missing_dependency")
    root = _resolve_project_path(db, project_id, None)
    try:
        return Repo(str(root))
    except Exception as e:
        raise AppError(f"Not a git repository: {e}", code="not_a_repo")


@router.get("/git/status", response_model=GitStatusOut)
def git_status(project_id: str, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    repo = _get_repo(db, project_id)
    branch = repo.active_branch.name if not repo.head.is_detached else "(detached)"
    untracked = repo.untracked_files
    modified = [item.a_path for item in repo.index.diff(None)]
    staged = [item.a_path for item in repo.index.diff("HEAD")] if repo.head.is_valid() else []
    ahead, behind = 0, 0
    try:
        if not repo.head.is_detached:
            tracking = repo.active_branch.tracking_branch()
            if tracking:
                ahead = sum(1 for _ in repo.iter_commits(f"{tracking}..{repo.active_branch}"))
                behind = sum(1 for _ in repo.iter_commits(f"{repo.active_branch}..{tracking}"))
    except Exception:
        pass
    return GitStatusOut(branch=branch, is_dirty=repo.is_dirty(untracked_files=True),
                       untracked=untracked, modified=modified, staged=staged,
                       ahead=ahead, behind=behind)


@router.post("/git/stage")
def git_stage(project_id: str, paths: list[str], db: Session = Depends(get_db),
              _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    repo = _get_repo(db, project_id)
    if paths:
        repo.git.add(paths)
    return {"staged": paths}


@router.post("/git/unstage")
def git_unstage(project_id: str, paths: list[str], db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    repo = _get_repo(db, project_id)
    if paths:
        repo.git.reset("HEAD", "--", *paths)
    return {"unstaged": paths}


@router.post("/git/commit", response_model=GitCommitOut)
def git_commit(project_id: str, payload: GitCommitIn, db: Session = Depends(get_db),
               current: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    import git as _git
    repo = _get_repo(db, project_id)
    if payload.add_all:
        repo.git.add(A=True)
    actor = _git.Actor(current.full_name or current.email, current.email)
    commit = repo.index.commit(payload.message, author=actor, committer=actor)
    return GitCommitOut(sha=commit.hexsha, message=commit.message,
                       author=current.email,
                       timestamp=datetime.now(timezone.utc))


@router.get("/git/log")
def git_log(project_id: str, limit: int = 50, db: Session = Depends(get_db),
            _: User = Depends(get_current_user)):
    repo = _get_repo(db, project_id)
    commits = []
    for c in list(repo.iter_commits(max_count=max(1, min(limit, 500)))):
        commits.append({
            "sha": c.hexsha[:10], "full_sha": c.hexsha,
            "author": f"{c.author.name} <{c.author.email}>",
            "date": c.committed_datetime.isoformat(),
            "message": c.message.strip().split("\n")[0],
            "body": c.message.strip(),
        })
    return {"branch": repo.active_branch.name if not repo.head.is_detached else None,
            "commits": commits}


@router.get("/git/diff")
def git_diff(project_id: str, path: str | None = None, staged: bool = False,
             db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    repo = _get_repo(db, project_id)
    args = ["--cached"] if staged else []
    if path:
        args.append("--")
        args.append(path)
    diff = repo.git.diff(*args) if args else repo.git.diff()
    return {"path": path, "staged": staged, "diff": diff}


@router.get("/git/branches")
def git_branches(project_id: str, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    repo = _get_repo(db, project_id)
    return {
        "current": repo.active_branch.name if not repo.head.is_detached else None,
        "local": [b.name for b in repo.branches],
        "remote": [b.name for b in repo.remote().refs] if repo.remotes else [],
    }


@router.post("/git/checkout")
def git_checkout(project_id: str, branch: str, create: bool = False,
                 db: Session = Depends(get_db),
                 _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    repo = _get_repo(db, project_id)
    if create:
        repo.git.checkout("-b", branch)
    else:
        repo.git.checkout(branch)
    return {"branch": branch}


@router.post("/git/push")
def git_push(project_id: str, payload: GitRemoteAction, db: Session = Depends(get_db),
             _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    repo = _get_repo(db, project_id)
    try:
        if payload.branch:
            info = repo.git.push(payload.remote, payload.branch)
        else:
            info = repo.git.push(payload.remote)
        return {"ok": True, "output": info}
    except Exception as e:
        raise AppError(f"git push failed: {e}", code="git_push_failed", status_code=500)


@router.post("/git/pull")
def git_pull(project_id: str, payload: GitRemoteAction, db: Session = Depends(get_db),
             _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    repo = _get_repo(db, project_id)
    try:
        info = repo.git.pull(payload.remote, payload.branch) if payload.branch \
               else repo.git.pull(payload.remote)
        return {"ok": True, "output": info}
    except Exception as e:
        raise AppError(f"git pull failed: {e}", code="git_pull_failed", status_code=500)


@router.post("/git/init")
def git_init(project_id: str, db: Session = Depends(get_db),
             _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    from git import Repo
    root = _resolve_project_path(db, project_id, None)
    if (root / ".git").exists():
        raise AppError("Already a git repository", code="exists", status_code=409)
    Repo.init(str(root))
    proj = db.get(CodeProject, project_id)
    if proj:
        proj.is_git = True
        db.commit()
    return {"ok": True}


# ---- 12. Snippets -------------------------------------------------------
@router.get("/snippets", response_model=list[CodeSnippetOut])
def list_snippets(q: str | None = None, language: str | None = None,
                  db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    stmt = (
        select(CodeSnippet)
        .where(or_(CodeSnippet.owner_id == current.id, CodeSnippet.is_public.is_(True)))
        .order_by(CodeSnippet.use_count.desc(), CodeSnippet.created_at.desc())
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(CodeSnippet.title.ilike(like),
                              CodeSnippet.code.ilike(like),
                              CodeSnippet.description.ilike(like)))
    if language:
        stmt = stmt.where(CodeSnippet.language == language)
    return db.scalars(stmt.limit(500)).all()


@router.post("/snippets", response_model=CodeSnippetOut)
def create_snippet(payload: CodeSnippetIn, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    obj = CodeSnippet(**payload.model_dump(), owner_id=current.id, use_count=0)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/snippets/{sid}", response_model=CodeSnippetOut)
def update_snippet(sid: str, payload: CodeSnippetIn, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    obj = db.get(CodeSnippet, sid)
    if not obj or (obj.owner_id and obj.owner_id != current.id):
        raise NotFoundError("Snippet not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/snippets/{sid}", status_code=204)
def delete_snippet(sid: str, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    obj = db.get(CodeSnippet, sid)
    if obj and (obj.owner_id is None or obj.owner_id == current.id):
        db.delete(obj)
        db.commit()


@router.post("/snippets/{sid}/use", response_model=CodeSnippetOut)
def use_snippet(sid: str, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    snippet = db.get(CodeSnippet, sid)
    if not snippet:
        raise NotFoundError("Snippet not found")
    snippet.use_count += 1
    db.commit()
    db.refresh(snippet)
    return snippet


@router.post("/snippets/suggest", response_model=SnippetSuggestOut)
def suggest_snippet(payload: SnippetSuggestIn, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    sys_msg = ("You generate reusable, well-tested code snippets. "
               "Return strict JSON only: "
               '{"title": "...", "code": "...", "language": "...", "description": "..."}')
    user_msg = (f"Create a {payload.language} snippet for: {payload.description}. "
                f"Keep it concise (under 60 lines), self-contained, with a one-line summary.")
    data = ai_svc.smart_json(
        user_msg, system=sys_msg, feature="snippet_suggest",
        provider=payload.provider, db=db, user_id=current.id, max_tokens=900,
        api_key_override=payload.api_key_override,
    )
    return SnippetSuggestOut(
        title=data.get("title", f"{payload.language} snippet"),
        code=data.get("code", "") or data.get("_raw", ""),
        language=data.get("language", payload.language),
        description=data.get("description", payload.description),
        provider=payload.provider or "anthropic",
    )


# ---- 13. API tester (Postman-like) --------------------------------------
@router.get("/api-requests", response_model=list[ApiRequestOut])
def list_api_requests(collection: str | None = None,
                      db: Session = Depends(get_db),
                      current: User = Depends(get_current_user)):
    stmt = (select(ApiRequest)
            .where(ApiRequest.owner_id == current.id)
            .order_by(ApiRequest.created_at.desc()))
    if collection:
        stmt = stmt.where(ApiRequest.collection == collection)
    return db.scalars(stmt).all()


@router.post("/api-requests", response_model=ApiRequestOut)
def save_api_request(payload: ApiRequestIn, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)):
    obj = ApiRequest(**payload.model_dump(), owner_id=current.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/api-requests/{rid}", response_model=ApiRequestOut)
def update_api_request(rid: str, payload: ApiRequestIn, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    obj = db.get(ApiRequest, rid)
    if not obj or obj.owner_id != current.id:
        raise NotFoundError("Request not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/api-requests/{rid}", status_code=204)
def delete_api_request(rid: str, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    obj = db.get(ApiRequest, rid)
    if obj and obj.owner_id == current.id:
        db.delete(obj)
        db.commit()


@router.post("/api-tester/execute", response_model=ApiExecOut)
def execute_request(payload: ApiExecIn, _: User = Depends(get_current_user)):
    started = time.time()
    try:
        r = httpx.request(
            payload.method.upper(), payload.url,
            headers=payload.headers or None,
            params=payload.params or None,
            content=payload.body.encode("utf-8") if payload.body else None,
            timeout=max(1, min(payload.timeout, 120)),
            follow_redirects=True,
        )
        duration_ms = int((time.time() - started) * 1000)
        body_bytes = r.content
        try:
            body_text = body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body_text = body_bytes.decode("utf-8", errors="replace")
        return ApiExecOut(
            status=r.status_code, headers=dict(r.headers),
            body=body_text[:500_000], duration_ms=duration_ms,
            size_bytes=len(body_bytes),
            content_type=r.headers.get("content-type"),
        )
    except httpx.HTTPError as e:
        raise AppError(f"Request failed: {e}", code="http_error")


# ---- 4. AI chat for coding (Claude/OpenAI/Ollama switch) ---------------
@router.post("/ai/chat", response_model=CodingChatOut)
def coding_chat(payload: CodingChatIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    context = _build_context_block(db, payload.project_id, payload.context_files)
    system = (
        "You are a senior pair programmer integrated into an IDE. Be concise, accurate, and "
        "actionable. When suggesting code, return it inside fenced ``` blocks labeled with the "
        "language. Always reference file paths verbatim. If the user pastes errors, diagnose them."
    )
    if context:
        system += "\n\nContext files attached:" + context
    messages = [ai_svc.AiMessage(role="system", content=system)]
    for m in payload.messages:
        messages.append(ai_svc.AiMessage(role=m.role, content=m.content))
    resp = ai_svc.call(
        messages, provider=payload.provider, model=payload.model,
        max_tokens=payload.max_tokens, temperature=payload.temperature,
        feature="coding_chat", db=db, user_id=current.id,
        api_key_override=payload.api_key_override,
    )
    return CodingChatOut(
        text=resp.text, provider=resp.provider, model=resp.model,
        tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
        latency_ms=resp.latency_ms,
    )


# ---- 5. Code generation -------------------------------------------------
@router.post("/ai/generate", response_model=CodeGenOut)
def code_generate(payload: CodeGenIn, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    context = _build_context_block(db, payload.project_id, payload.context_files)
    sys_msg = ("You are an expert pair programmer. Output one fenced code block (no other "
               "text inside it), then a 2-4 sentence explanation below it. Be concise.")
    user_msg = (f"Generate {payload.language or ''} code for:\n{payload.prompt}\n\n"
                f"{('Context:' + context) if context else ''}").strip()
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="system", content=sys_msg),
         ai_svc.AiMessage(role="user", content=user_msg)],
        provider=payload.provider, model=payload.model,
        feature="code_generate", db=db, user_id=current.id, max_tokens=2000,
        api_key_override=payload.api_key_override,
    )
    code, explanation = _extract_first_codeblock(resp.text)
    return CodeGenOut(code=code, explanation=explanation,
                      provider=resp.provider, model=resp.model)


# ---- 6. Explain + Docstring generator -----------------------------------
@router.post("/ai/explain", response_model=ExplainCodeOut)
def code_explain(payload: ExplainCodeIn, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    prompt = (f"Explain this {payload.language} code step by step. Be precise. Call out side "
              f"effects, complexity, and any pitfalls.\n\n```{payload.language}\n{payload.code}\n```")
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="user", content=prompt)],
        provider=payload.provider, model=payload.model,
        feature="code_explain", db=db, user_id=current.id, max_tokens=1200,
        api_key_override=payload.api_key_override,
    )
    return ExplainCodeOut(explanation=resp.text, provider=resp.provider, model=resp.model)


@router.post("/ai/docstring", response_model=DocstringOut)
def code_docstring(payload: DocstringIn, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    sys_msg = ("You add idiomatic documentation. Return the exact original code with "
               "inline docstrings/comments added (no other prose). Output one fenced code block.")
    user_msg = (f"Add {payload.style}-style docstrings/comments to this {payload.language} code. "
                f"Document every function, class, parameter, and return value. Do not change behavior.\n\n"
                f"```{payload.language}\n{payload.code}\n```")
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="system", content=sys_msg),
         ai_svc.AiMessage(role="user", content=user_msg)],
        provider=payload.provider, feature="code_docstring",
        db=db, user_id=current.id, max_tokens=2400,
        api_key_override=payload.api_key_override,
    )
    documented, _ = _extract_first_codeblock(resp.text)
    return DocstringOut(documented_code=documented or resp.text,
                        provider=resp.provider, model=resp.model)


# ---- 7. Bug detector + auto-fixer ---------------------------------------
@router.post("/ai/bugfix", response_model=BugFixOut)
def code_bugfix(payload: BugFixIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    err = f"\n\nError encountered:\n{payload.error}" if payload.error else ""
    sys_msg = ("You are a senior debugger. Return one fenced code block containing the fixed "
               "code only, followed by a short explanation outside the block.")
    user_msg = (f"Fix the following {payload.language} code.{err}\n\n"
                f"```{payload.language}\n{payload.code}\n```")
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="system", content=sys_msg),
         ai_svc.AiMessage(role="user", content=user_msg)],
        provider=payload.provider, model=payload.model,
        feature="code_bugfix", db=db, user_id=current.id, max_tokens=2000,
        api_key_override=payload.api_key_override,
    )
    fixed, explanation = _extract_first_codeblock(resp.text)
    return BugFixOut(fixed_code=fixed or resp.text, explanation=explanation,
                     provider=resp.provider, model=resp.model)


# ---- 8. Code review -----------------------------------------------------
@router.post("/ai/review", response_model=CodeReviewOut)
def code_review(payload: CodeReviewIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    focus = payload.focus or "general quality, correctness, performance, security, style"
    sys_msg = "You are a strict senior code reviewer. Output strict JSON, no markdown fences."
    user_msg = (
        f"Review this {payload.language} code focusing on: {focus}. "
        "Return JSON ONLY with shape "
        '{"summary": "<one paragraph>", "findings": [{"line": int|null, '
        '"severity": "low|medium|high", "category": "bug|security|performance|style|design", '
        '"message": "<finding>", "suggestion": "<concrete fix>"}]}\n\n'
        f"```{payload.language}\n{payload.code}\n```"
    )
    data = ai_svc.smart_json(
        user_msg, system=sys_msg, feature="code_review",
        provider=payload.provider, db=db, user_id=current.id, max_tokens=2400,
        api_key_override=payload.api_key_override,
    )
    findings_raw = data.get("findings", [])
    findings = []
    for f in findings_raw:
        if isinstance(f, dict):
            findings.append(CodeReviewFinding(
                line=f.get("line"),
                severity=str(f.get("severity", "medium")).lower(),
                category=str(f.get("category", "general")),
                message=str(f.get("message", "")),
                suggestion=f.get("suggestion"),
            ))
    return CodeReviewOut(
        summary=data.get("summary", "")[:2000] or data.get("_raw", "")[:2000],
        findings=findings,
        provider=payload.provider or "anthropic",
        model=payload.model or "",
    )


# ---- 9. Multi-file edit with AI context ---------------------------------
@router.post("/ai/multi-file-plan", response_model=MultiFileEditOut)
def multi_file_plan(payload: MultiFileEditIn, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    """Ask AI to plan a multi-file edit. Returns a list of file changes without applying."""
    context = _build_context_block(db, payload.project_id, payload.context_files,
                                   limit_per_file=20_000)
    target_block = ""
    for f in payload.target_files[:6]:
        try:
            p = _resolve_project_path(db, payload.project_id, f)
            if p.exists() and p.is_file():
                lang = _detect_language(p) or ""
                target_block += f"\n\n#### TARGET FILE: {f}\n```{lang}\n{_read_text_safe(p, 30_000)}\n```"
            else:
                target_block += f"\n\n#### TARGET FILE (new): {f}"
        except Exception:
            target_block += f"\n\n#### TARGET FILE: {f}"
    sys_msg = (
        "You edit multiple files in lockstep inside a software project. "
        "Return STRICT JSON only — no markdown fences — with shape:\n"
        '{"summary": "<one paragraph describing the change>",\n'
        ' "changes": [{"path": "<relative path>", "content": "<full new file content>", "create_if_missing": true}]}\n'
        "Always emit complete file contents (not diffs). Preserve unrelated code. "
        "Only modify the files that need to change."
    )
    user_msg = (
        f"Task: {payload.prompt}\n\n"
        f"Context files (read-only for reference):{context}\n\n"
        f"Target files (you may modify these):{target_block}"
    )
    raw = ai_svc.call(
        [ai_svc.AiMessage(role="system", content=sys_msg),
         ai_svc.AiMessage(role="user", content=user_msg)],
        feature="multi_file_edit", db=db, user_id=current.id, max_tokens=8000,
    )
    cleaned = _strip_code_block(raw.text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to locate JSON object boundary
        i, j = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= i < j:
            try:
                data = json.loads(cleaned[i:j + 1])
            except json.JSONDecodeError:
                raise AppError("AI did not return valid JSON for multi-file edit",
                              code="ai_parse_error")
        else:
            raise AppError("AI did not return valid JSON for multi-file edit",
                          code="ai_parse_error")
    changes = []
    for c in data.get("changes", []):
        if isinstance(c, dict) and c.get("path") and "content" in c:
            changes.append(FilePatchOp(
                path=c["path"], content=c["content"],
                create_if_missing=bool(c.get("create_if_missing", True)),
            ))
    return MultiFileEditOut(
        summary=data.get("summary", "Multi-file change plan"),
        changes=changes, provider=raw.provider, model=raw.model,
    )


@router.post("/ai/multi-file-apply")
def multi_file_apply(payload: MultiFileApplyIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    applied = []
    for change in payload.changes:
        p = _resolve_project_path(db, payload.project_id, change.path)
        if not p.exists() and not change.create_if_missing:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(change.content, encoding="utf-8")
        applied.append(str(p))
    return {"applied": applied, "count": len(applied)}


# ---- 15. Regex builder --------------------------------------------------
@router.post("/regex/explain", response_model=RegexExplainBuilderOut)
def regex_explain(payload: RegexExplainBuilderIn, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    sys_msg = (
        "You teach regex precisely. Return strict JSON only: "
        '{"explanation": "<step-by-step plain English>", "test_cases": [{"input": "...", "should_match": true|false, "note": "..."}]}'
    )
    user_msg = (f"Explain this regex pattern (flags: '{payload.flags}'):\n\n{payload.pattern}\n\n"
                "Provide 3-5 example inputs that should and shouldn't match.")
    data = ai_svc.smart_json(
        user_msg, system=sys_msg, feature="regex_explain",
        provider=payload.provider, db=db, user_id=current.id, max_tokens=900,
        api_key_override=payload.api_key_override,
    )
    return RegexExplainBuilderOut(
        pattern=payload.pattern, flags=payload.flags,
        explanation=data.get("explanation", "") or data.get("_raw", ""),
        test_cases=data.get("test_cases", []) if isinstance(data.get("test_cases"), list) else [],
        provider=payload.provider or "anthropic",
    )


@router.post("/regex/test", response_model=RegexTestOut)
def regex_test(payload: RegexTestIn, _: User = Depends(get_current_user)):
    flag_bits = 0
    if "i" in payload.flags: flag_bits |= re.IGNORECASE
    if "m" in payload.flags: flag_bits |= re.MULTILINE
    if "s" in payload.flags: flag_bits |= re.DOTALL
    if "x" in payload.flags: flag_bits |= re.VERBOSE
    if "a" in payload.flags: flag_bits |= re.ASCII
    if "u" in payload.flags: flag_bits |= re.UNICODE
    try:
        pat = re.compile(payload.pattern, flag_bits)
    except re.error as e:
        return RegexTestOut(matches=[], is_valid=False, error=str(e))
    matches: list[RegexMatch] = []
    for m in pat.finditer(payload.text):
        matches.append(RegexMatch(
            match=m.group(0), start=m.start(), end=m.end(),
            groups=[g if g is not None else "" for g in m.groups()],
        ))
    replaced = None
    if payload.replacement is not None:
        try:
            replaced = pat.sub(payload.replacement, payload.text)
        except re.error as e:
            return RegexTestOut(matches=matches, is_valid=True, error=str(e), replaced=None)
    return RegexTestOut(matches=matches, is_valid=True, replaced=replaced)


@router.post("/regex/from-description", response_model=RegexFromDescriptionOut)
def regex_from_description(payload: RegexFromDescriptionIn,
                           db: Session = Depends(get_db),
                           current: User = Depends(get_current_user)):
    sys_msg = (
        "You translate natural-language requirements into Python-compatible regular expressions. "
        "Return strict JSON only: "
        '{"pattern": "<regex>", "flags": "<imsx letters>", "explanation": "<one paragraph>"}'
    )
    user_msg = (
        f"Build a regex for: {payload.description}\n\n"
        f"Should match (examples):\n{json.dumps(payload.examples_match)}\n"
        f"Should NOT match:\n{json.dumps(payload.examples_no_match)}\n\n"
        f"Make it concise and correct. Use named groups when helpful."
    )
    data = ai_svc.smart_json(
        user_msg, system=sys_msg, feature="regex_build",
        provider=payload.provider, db=db, user_id=current.id, max_tokens=600,
        api_key_override=payload.api_key_override,
    )
    return RegexFromDescriptionOut(
        pattern=data.get("pattern", "") or data.get("_raw", ""),
        flags=data.get("flags", ""),
        explanation=data.get("explanation", ""),
        provider=payload.provider or "anthropic",
    )


@router.get("/regex/library", response_model=list[RegexLibraryOut])
def list_regex_library(db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    return db.scalars(
        select(RegexLibraryEntry).where(RegexLibraryEntry.owner_id == current.id)
        .order_by(RegexLibraryEntry.created_at.desc())
    ).all()


@router.post("/regex/library", response_model=RegexLibraryOut)
def save_regex_library(payload: RegexLibraryIn, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    obj = RegexLibraryEntry(**payload.model_dump(), owner_id=current.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/regex/library/{rid}", status_code=204)
def delete_regex_library(rid: str, db: Session = Depends(get_db),
                         current: User = Depends(get_current_user)):
    obj = db.get(RegexLibraryEntry, rid)
    if obj and obj.owner_id == current.id:
        db.delete(obj)
        db.commit()


# ---- 14. Database query builder + visualizer ----------------------------
@router.post("/ai/db-query", response_model=DBQueryOut)
def db_query_builder(payload: DBQueryIn, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)):
    schema_block = f"\n\nSchema:\n{payload.schema_hint}\n" if payload.schema_hint else ""
    prompt = (
        f"Generate a {payload.dialect} SQL query for this natural-language request. "
        "Return JSON only with shape: "
        '{"sql": "...", "explanation": "..."}\n\n'
        f"REQUEST: {payload.description}{schema_block}"
    )
    data = ai_svc.smart_json(
        prompt, system="You are a SQL expert. Output strict JSON only.",
        feature="db_query", provider=payload.provider,
        db=db, user_id=current.id, max_tokens=900,
        api_key_override=payload.api_key_override,
    )
    return DBQueryOut(
        sql=data.get("sql", "") or data.get("_raw", ""),
        explanation=data.get("explanation", ""),
        provider=payload.provider or "anthropic",
    )


@router.get("/db/connections", response_model=list[DBConnectionOut])
def list_db_connections(db: Session = Depends(get_db),
                        current: User = Depends(get_current_user)):
    return db.scalars(
        select(DatabaseConnection).where(DatabaseConnection.owner_id == current.id)
        .order_by(DatabaseConnection.created_at.desc())
    ).all()


@router.post("/db/connections", response_model=DBConnectionOut)
def create_db_connection(payload: DBConnectionIn, db: Session = Depends(get_db),
                         current: User = Depends(get_current_user)):
    obj = DatabaseConnection(
        name=payload.name, dialect=payload.dialect,
        dsn_encrypted=encrypt_text(payload.dsn), owner_id=current.id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/db/connections/{cid}", status_code=204)
def delete_db_connection(cid: str, db: Session = Depends(get_db),
                         current: User = Depends(get_current_user)):
    obj = db.get(DatabaseConnection, cid)
    if obj and obj.owner_id == current.id:
        db.delete(obj)
        db.commit()


def _build_engine(conn: DatabaseConnection):
    from sqlalchemy import create_engine
    dsn = decrypt_text(conn.dsn_encrypted)
    return create_engine(dsn, pool_pre_ping=True, future=True)


@router.get("/db/connections/{cid}/schema", response_model=DBSchemaOut)
def db_introspect(cid: str, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    conn = db.get(DatabaseConnection, cid)
    if not conn or conn.owner_id != current.id:
        raise NotFoundError("Connection not found")
    from sqlalchemy import inspect as sa_inspect
    try:
        engine = _build_engine(conn)
        inspector = sa_inspect(engine)
        tables: list[DBSchemaTable] = []
        for tname in inspector.get_table_names():
            cols = [
                {"name": c["name"], "type": str(c["type"]),
                 "nullable": c.get("nullable", True),
                 "default": str(c.get("default")) if c.get("default") is not None else None}
                for c in inspector.get_columns(tname)
            ]
            pk = inspector.get_pk_constraint(tname).get("constrained_columns", [])
            fks = [
                {"columns": fk.get("constrained_columns", []),
                 "referred_table": fk.get("referred_table"),
                 "referred_columns": fk.get("referred_columns", [])}
                for fk in inspector.get_foreign_keys(tname)
            ]
            tables.append(DBSchemaTable(name=tname, columns=cols,
                                        primary_key=pk, foreign_keys=fks))
        engine.dispose()
        return DBSchemaOut(dialect=conn.dialect, tables=tables)
    except Exception as e:
        raise AppError(f"Schema introspection failed: {e}",
                      code="db_introspect_failed", status_code=500)


@router.post("/db/execute", response_model=DBExecuteOut)
def db_execute(payload: DBExecuteIn, db: Session = Depends(get_db),
               current: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    conn = db.get(DatabaseConnection, payload.connection_id)
    if not conn or conn.owner_id != current.id:
        raise NotFoundError("Connection not found")
    from sqlalchemy import text
    engine = _build_engine(conn)
    started = time.time()
    truncated = False
    try:
        with engine.connect() as c:
            result = c.execute(text(payload.sql))
            try:
                columns = list(result.keys())
            except Exception:
                columns = []
            rows: list[list[Any]] = []
            if result.returns_rows:
                limit = max(1, min(payload.limit, 5000))
                fetched = result.fetchmany(limit + 1)
                if len(fetched) > limit:
                    truncated = True
                    fetched = fetched[:limit]
                for row in fetched:
                    rows.append([_jsonable(v) for v in row])
            try:
                c.commit()
            except Exception:
                pass
        engine.dispose()
        duration_ms = int((time.time() - started) * 1000)
        return DBExecuteOut(columns=columns, rows=rows, row_count=len(rows),
                            duration_ms=duration_ms, truncated=truncated)
    except Exception as e:
        engine.dispose()
        raise AppError(f"Query failed: {e}", code="db_query_failed", status_code=500)


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (datetime,)):
        return v.isoformat()
    try:
        return str(v)
    except Exception:
        return repr(v)


# ---- 11. Syntax highlighting registry ----------------------------------
@router.get("/languages")
def supported_languages(_: User = Depends(get_current_user)):
    """Return the set of Monaco-compatible languages this backend recognises."""
    seen: set[str] = set()
    items: list[dict] = []
    for ext, lang in sorted(LANGUAGE_BY_EXT.items()):
        if lang in seen:
            continue
        seen.add(lang)
        items.append({"language": lang, "sample_extension": ext})
    return {"count": len(items), "languages": items}
