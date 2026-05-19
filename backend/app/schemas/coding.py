"""AI Coding Assistant schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CodeProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=500)
    description: str | None = None
    language_primary: str | None = None


class CodeProjectOut(ORMModel):
    id: str
    name: str
    path: str
    description: str | None
    language_primary: str | None
    is_git: bool


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    children: list["FileNode"] | None = None


FileNode.model_rebuild()


class FileContent(BaseModel):
    path: str
    content: str
    language: str | None = None


class FileSaveIn(BaseModel):
    path: str
    content: str


class CodeSnippetIn(BaseModel):
    title: str
    language: str = "text"
    code: str
    description: str | None = None
    tags: list[str] = []
    is_public: bool = False


class CodeSnippetOut(ORMModel):
    id: str
    title: str
    language: str
    code: str
    description: str | None
    is_public: bool
    use_count: int


class TerminalCommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    cwd: str | None = None
    timeout_seconds: int = 30


class TerminalCommandOut(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class GitStatusOut(BaseModel):
    branch: str
    is_dirty: bool
    untracked: list[str]
    modified: list[str]
    staged: list[str]
    ahead: int
    behind: int


class GitCommitIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    add_all: bool = False


class GitCommitOut(BaseModel):
    sha: str
    message: str
    author: str
    timestamp: datetime


class GitDiffOut(BaseModel):
    path: str
    diff: str


class ApiRequestIn(BaseModel):
    name: str
    method: str = "GET"
    url: str
    headers: dict[str, str] | None = None
    params: dict[str, str] | None = None
    body: str | None = None
    collection: str | None = None


class ApiRequestOut(ORMModel):
    id: str
    name: str
    method: str
    url: str
    headers: dict[str, str] | None
    params: dict[str, str] | None
    body: str | None
    collection: str | None


class ApiExecIn(BaseModel):
    method: str = "GET"
    url: str
    headers: dict[str, str] | None = None
    params: dict[str, str] | None = None
    body: str | None = None
    timeout: int = 20


class ApiExecOut(BaseModel):
    status: int
    headers: dict[str, str]
    body: str
    duration_ms: int


class CodeGenIn(BaseModel):
    prompt: str = Field(min_length=1)
    language: str | None = None
    context_files: list[str] | None = None
    project_id: str | None = None


class CodeGenOut(BaseModel):
    code: str
    explanation: str
    provider: str
    model: str


class CodeReviewIn(BaseModel):
    code: str
    language: str = "python"
    focus: str | None = None  # security|performance|style|bugs


class CodeReviewOut(BaseModel):
    summary: str
    findings: list[dict] = []
    provider: str


class BugFixIn(BaseModel):
    code: str
    error: str | None = None
    language: str = "python"


class BugFixOut(BaseModel):
    fixed_code: str
    explanation: str
    diff: str | None = None
    provider: str


class ExplainCodeIn(BaseModel):
    code: str
    language: str = "python"


class DBQueryIn(BaseModel):
    description: str  # plain English request
    dialect: str = "postgresql"  # postgresql|mysql|sqlite|sqlserver


class DBQueryOut(BaseModel):
    sql: str
    explanation: str
