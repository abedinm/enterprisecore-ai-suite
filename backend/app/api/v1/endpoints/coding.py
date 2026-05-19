"""AI Coding Assistant — IDE, file explorer, terminal, git, AI codegen."""
from __future__ import annotations

import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.db.session import get_db
from app.models.coding import ApiRequest, CodeProject, CodeSnippet, GitRepo
from app.models.user import User, UserRole
from app.schemas.coding import (
    ApiExecIn, ApiExecOut, ApiRequestIn, ApiRequestOut, BugFixIn, BugFixOut,
    CodeGenIn, CodeGenOut, CodeProjectIn, CodeProjectOut, CodeReviewIn,
    CodeReviewOut, CodeSnippetIn, CodeSnippetOut, DBQueryIn, DBQueryOut,
    ExplainCodeIn, FileContent, FileNode, FileSaveIn, GitCommitIn, GitCommitOut,
    GitStatusOut, TerminalCommandIn, TerminalCommandOut,
)
from app.services import ai as ai_svc

router = APIRouter()

LANGUAGE_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".h": "cpp", ".hpp": "cpp",
    ".html": "html", ".css": "css", ".scss": "scss", ".json": "json", ".yaml": "yaml",
    ".yml": "yaml", ".md": "markdown", ".sql": "sql", ".sh": "shell", ".ps1": "powershell",
    ".kt": "kotlin", ".swift": "swift", ".php": "php", ".lua": "lua", ".pl": "perl",
    ".r": "r", ".scala": "scala", ".dart": "dart", ".vue": "vue", ".svelte": "svelte",
    ".xml": "xml", ".toml": "toml", ".ini": "ini", ".dockerfile": "dockerfile",
    ".tf": "hcl", ".tfvars": "hcl", ".graphql": "graphql", ".proto": "protobuf",
}
DEFAULT_IGNORE = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
                  "dist", "build", ".idea", ".vscode", ".next", ".nuxt", "out",
                  ".turbo", "coverage"}


# ---- Helpers ------------------------------------------------------------
def _resolve_project_path(db: Session, project_id: str | None, path: str | None) -> Path:
    """Resolve a request path within a project's tree. Prevents escape via .."""
    if not project_id and not path:
        raise AppError("project_id or absolute path required", code="bad_request")
    if project_id:
        proj = db.get(CodeProject, project_id)
        if not proj:
            raise NotFoundError("Code project not found")
        root = Path(proj.path).expanduser().resolve()
        if path:
            candidate = (root / path.lstrip("/\\")).resolve()
            if root not in candidate.parents and candidate != root:
                raise AppError("Path is outside project root", code="path_traversal", status_code=403)
            return candidate
        return root
    return Path(path).expanduser().resolve()  # standalone mode (no jail)


def _read_text_safe(p: Path, limit_bytes: int = 2_000_000) -> str:
    if p.stat().st_size > limit_bytes:
        raise AppError(f"File too large to load ({p.stat().st_size} bytes; limit {limit_bytes})", code="too_large")
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_bytes().decode("utf-8", errors="replace")


def _detect_language(p: Path) -> str | None:
    return LANGUAGE_BY_EXT.get(p.suffix.lower())


# ---- Projects -----------------------------------------------------------
@router.get("/projects", response_model=list[CodeProjectOut])
def list_code_projects(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(CodeProject).order_by(CodeProject.created_at.desc())).all()


@router.post("/projects", response_model=CodeProjectOut)
def create_code_project(payload: CodeProjectIn, db: Session = Depends(get_db),
                        current: User = Depends(get_current_user)):
    root = Path(payload.path).expanduser().resolve()
    if not root.exists():
        raise AppError(f"Path does not exist: {root}", code="path_not_found")
    proj = CodeProject(
        name=payload.name, path=str(root), description=payload.description,
        language_primary=payload.language_primary, owner_id=current.id,
        is_git=(root / ".git").exists(),
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


# ---- File tree / read / write ------------------------------------------
@router.get("/tree", response_model=FileNode)
def file_tree(project_id: str, path: str | None = None, depth: int = 2,
              db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    root = _resolve_project_path(db, project_id, path)
    if not root.exists():
        raise NotFoundError("Path not found")

    def _build(p: Path, remaining_depth: int) -> FileNode:
        node = FileNode(
            name=p.name or str(p),
            path=str(p),
            is_dir=p.is_dir(),
            size=p.stat().st_size if p.is_file() else None,
        )
        if p.is_dir() and remaining_depth > 0:
            children = []
            try:
                for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    if child.name in DEFAULT_IGNORE or child.name.startswith("."):
                        continue
                    children.append(_build(child, remaining_depth - 1))
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
    return FileContent(path=str(p), content=_read_text_safe(p), language=_detect_language(p))


@router.post("/file")
def save_file(payload: FileSaveIn, project_id: str, db: Session = Depends(get_db),
              _: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    p = _resolve_project_path(db, project_id, payload.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload.content, encoding="utf-8")
    return {"path": str(p), "size": p.stat().st_size}


# ---- Terminal -----------------------------------------------------------
TERMINAL_BLOCKLIST = {"rm", "del", "format", "mkfs", "dd", "shutdown", "reboot", "poweroff"}


@router.post("/terminal", response_model=TerminalCommandOut)
def run_command(payload: TerminalCommandIn, project_id: str | None = None,
                db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.developer, UserRole.admin))):
    """Execute a command in the user's project sandbox. Blocks obviously destructive verbs."""
    cwd = _resolve_project_path(db, project_id, payload.cwd) if project_id else None
    if cwd is not None and not cwd.exists():
        raise NotFoundError("Working directory not found")
    first_token = shlex.split(payload.command)[0] if payload.command.strip() else ""
    base = Path(first_token).name.lower()
    if base in TERMINAL_BLOCKLIST:
        raise AppError("Destructive command is blocked", code="command_blocked", status_code=403)
    started = time.time()
    try:
        result = subprocess.run(
            payload.command,
            shell=True,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=max(1, min(payload.timeout_seconds, 120)),
        )
    except subprocess.TimeoutExpired:
        raise AppError("Command timed out", code="timeout", status_code=408)
    duration_ms = int((time.time() - started) * 1000)
    return TerminalCommandOut(
        stdout=result.stdout[-30_000:], stderr=result.stderr[-10_000:],
        exit_code=result.returncode, duration_ms=duration_ms,
    )


# ---- Git integration ----------------------------------------------------
@router.get("/git/status", response_model=GitStatusOut)
def git_status(project_id: str, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    try:
        from git import Repo
    except ImportError:
        raise AppError("GitPython is not installed", code="missing_dependency")
    root = _resolve_project_path(db, project_id, None)
    try:
        repo = Repo(str(root))
    except Exception as e:
        raise AppError(f"Not a git repository: {e}", code="not_a_repo")
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


@router.post("/git/commit", response_model=GitCommitOut)
def git_commit(project_id: str, payload: GitCommitIn, db: Session = Depends(get_db),
               current: User = Depends(require_roles(UserRole.developer, UserRole.admin, UserRole.manager))):
    from git import Repo
    root = _resolve_project_path(db, project_id, None)
    repo = Repo(str(root))
    if payload.add_all:
        repo.git.add(A=True)
    commit = repo.index.commit(payload.message,
                               author=__import__("git").Actor(current.full_name, current.email))
    return GitCommitOut(sha=commit.hexsha, message=commit.message,
                       author=current.email, timestamp=datetime.now(timezone.utc))


@router.get("/git/log")
def git_log(project_id: str, limit: int = 50, db: Session = Depends(get_db),
            _: User = Depends(get_current_user)):
    from git import Repo
    root = _resolve_project_path(db, project_id, None)
    repo = Repo(str(root))
    commits = []
    for c in list(repo.iter_commits(max_count=limit)):
        commits.append({
            "sha": c.hexsha[:10], "full_sha": c.hexsha,
            "author": f"{c.author.name} <{c.author.email}>",
            "date": c.committed_datetime.isoformat(),
            "message": c.message.strip().split("\n")[0],
        })
    return {"branch": repo.active_branch.name if not repo.head.is_detached else None, "commits": commits}


@router.get("/git/diff")
def git_diff(project_id: str, path: str | None = None, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    from git import Repo
    root = _resolve_project_path(db, project_id, None)
    repo = Repo(str(root))
    diff = repo.git.diff(path) if path else repo.git.diff()
    return {"path": path, "diff": diff}


# ---- Snippets -----------------------------------------------------------
@router.get("/snippets", response_model=list[CodeSnippetOut])
def list_snippets(q: str | None = None, language: str | None = None,
                  db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    stmt = (
        select(CodeSnippet)
        .where(or_(CodeSnippet.owner_id == current.id, CodeSnippet.is_public.is_(True)))
        .order_by(CodeSnippet.use_count.desc(), CodeSnippet.created_at.desc())
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(CodeSnippet.title.ilike(like), CodeSnippet.code.ilike(like)))
    if language:
        stmt = stmt.where(CodeSnippet.language == language)
    return db.scalars(stmt.limit(500)).all()


@router.post("/snippets", response_model=CodeSnippetOut)
def create_snippet(payload: CodeSnippetIn, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    data = payload.model_dump()
    data["tags"] = data.get("tags") or []
    obj = CodeSnippet(**data, owner_id=current.id, use_count=0)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/snippets/{sid}/use")
def use_snippet(sid: str, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    snippet = db.get(CodeSnippet, sid)
    if not snippet:
        raise NotFoundError("Snippet not found")
    snippet.use_count += 1
    db.commit()
    return {"id": snippet.id, "use_count": snippet.use_count}


# ---- API tester ---------------------------------------------------------
@router.get("/api-requests", response_model=list[ApiRequestOut])
def list_api_requests(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return db.scalars(
        select(ApiRequest).where(ApiRequest.owner_id == current.id).order_by(ApiRequest.created_at.desc())
    ).all()


@router.post("/api-requests", response_model=ApiRequestOut)
def save_api_request(payload: ApiRequestIn, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)):
    obj = ApiRequest(**payload.model_dump(), owner_id=current.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/api-tester/execute", response_model=ApiExecOut)
def execute_request(payload: ApiExecIn, _: User = Depends(get_current_user)):
    started = time.time()
    try:
        r = httpx.request(
            payload.method.upper(), payload.url,
            headers=payload.headers or None, params=payload.params or None,
            content=payload.body.encode("utf-8") if payload.body else None,
            timeout=min(payload.timeout, 60),
        )
        duration_ms = int((time.time() - started) * 1000)
        body = r.text
        return ApiExecOut(
            status=r.status_code, headers=dict(r.headers),
            body=body[:200_000], duration_ms=duration_ms,
        )
    except httpx.HTTPError as e:
        raise AppError(f"Request failed: {e}", code="http_error")


# ---- AI coding features -------------------------------------------------
def _strip_code_block(text: str) -> str:
    """Strip ```lang\n...\n``` fences if present."""
    t = text.strip()
    if t.startswith("```"):
        t = t.lstrip("`")
        if "\n" in t:
            t = t.split("\n", 1)[1]
        if t.endswith("```"):
            t = t[:-3].rstrip()
    return t


@router.post("/ai/generate", response_model=CodeGenOut)
def code_generate(payload: CodeGenIn, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    context = ""
    if payload.project_id and payload.context_files:
        for f in payload.context_files[:5]:
            try:
                p = _resolve_project_path(db, payload.project_id, f)
                if p.exists() and p.is_file():
                    context += f"\n\n### {f}\n```{_detect_language(p) or ''}\n{_read_text_safe(p, 50_000)}\n```"
            except Exception:
                continue
    sys_msg = ("You are an expert pair programmer. Output the requested code only inside one fenced "
               "code block, followed by a brief 2-4 sentence explanation. Be concise.")
    user_msg = f"Generate {payload.language or ''} code for:\n{payload.prompt}\n\nProject context:{context}"
    resp = ai_svc.call(
        [ai_svc.AiMessage(role="system", content=sys_msg),
         ai_svc.AiMessage(role="user", content=user_msg)],
        feature="code_generate", db=db, user_id=current.id, max_tokens=1500,
    )
    text = resp.text
    code, _, explanation = text.partition("```")
    if "```" in text:
        # Extract the first ```...```
        body = text.split("```", 2)
        if len(body) >= 3:
            block = body[1]
            if "\n" in block:
                block = block.split("\n", 1)[1]
            code = block.rsplit("```", 1)[0].rstrip()
            explanation = body[2].strip()
    else:
        code = text
        explanation = ""
    return CodeGenOut(code=code, explanation=explanation, provider=resp.provider, model=resp.model)


@router.post("/ai/explain")
def code_explain(payload: ExplainCodeIn, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    prompt = f"Explain this {payload.language} code step by step.\n\n```{payload.language}\n{payload.code}\n```"
    resp = ai_svc.call([ai_svc.AiMessage(role="user", content=prompt)],
                       feature="code_explain", db=db, user_id=current.id, max_tokens=800)
    return {"explanation": resp.text, "provider": resp.provider}


@router.post("/ai/review", response_model=CodeReviewOut)
def code_review(payload: CodeReviewIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    focus = payload.focus or "general quality, bugs, and security"
    prompt = (
        f"Review this {payload.language} code, focusing on: {focus}. "
        f"Return JSON ONLY (no markdown) with shape "
        '{"summary": "...", "findings": [{"line": int|null, "severity": "low|medium|high", "category": "...", "message": "...", "suggestion": "..."}]}\n\n'
        f"```{payload.language}\n{payload.code}\n```"
    )
    resp = ai_svc.smart_text(prompt, feature="code_review", db=db, user_id=current.id, max_tokens=1500,
                            system="You are a senior code reviewer. Output strict JSON.")
    import json
    cleaned = _strip_code_block(resp)
    try:
        data = json.loads(cleaned)
        return CodeReviewOut(summary=data.get("summary", ""), findings=data.get("findings", []),
                            provider="ai")
    except json.JSONDecodeError:
        return CodeReviewOut(summary=resp[:1000], findings=[], provider="ai")


@router.post("/ai/bugfix", response_model=BugFixOut)
def code_bugfix(payload: BugFixIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    err = f"\n\nError encountered:\n{payload.error}" if payload.error else ""
    prompt = (
        f"Fix the following {payload.language} code.{err}\n\n"
        f"Return the fixed code in a single ``` block, followed by a 2-4 sentence explanation.\n\n"
        f"```{payload.language}\n{payload.code}\n```"
    )
    resp = ai_svc.call([ai_svc.AiMessage(role="user", content=prompt)],
                       feature="code_bugfix", db=db, user_id=current.id, max_tokens=1500)
    text = resp.text
    fixed = _strip_code_block(text)
    if "```" in text:
        body = text.split("```", 2)
        if len(body) >= 3:
            block = body[1]
            if "\n" in block:
                block = block.split("\n", 1)[1]
            fixed = block.rsplit("```", 1)[0].rstrip()
    return BugFixOut(fixed_code=fixed, explanation="", provider=resp.provider)


@router.post("/ai/db-query", response_model=DBQueryOut)
def db_query_builder(payload: DBQueryIn, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)):
    prompt = (
        f"Generate a {payload.dialect} SQL query for this natural-language request. "
        f"Return JSON only with shape: "
        '{"sql": "...", "explanation": "..."}\n\n'
        f"REQUEST: {payload.description}"
    )
    raw = ai_svc.smart_text(prompt, feature="db_query", db=db, user_id=current.id, max_tokens=800,
                           system="You are a SQL expert. Output strict JSON only.")
    cleaned = _strip_code_block(raw)
    import json
    try:
        data = json.loads(cleaned)
        return DBQueryOut(sql=data.get("sql", ""), explanation=data.get("explanation", ""))
    except json.JSONDecodeError:
        return DBQueryOut(sql=raw, explanation="")
