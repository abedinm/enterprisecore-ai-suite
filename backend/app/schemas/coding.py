"""AI Coding Assistant schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---- Projects ----------------------------------------------------------
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
    created_at: datetime
    updated_at: datetime


# ---- File tree / editor ------------------------------------------------
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
    size: int | None = None


class FileSaveIn(BaseModel):
    path: str
    content: str


class FilePatchOp(BaseModel):
    """Single file change in a multi-file edit operation."""
    path: str
    content: str
    create_if_missing: bool = True


class MultiFileEditIn(BaseModel):
    project_id: str
    prompt: str
    context_files: list[str] = []
    target_files: list[str] = []


class MultiFileEditOut(BaseModel):
    summary: str
    changes: list[FilePatchOp]
    provider: str
    model: str


class MultiFileApplyIn(BaseModel):
    project_id: str
    changes: list[FilePatchOp]


# ---- Snippets ----------------------------------------------------------
class CodeSnippetIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    language: str = Field(default="text", max_length=40)
    code: str = Field(min_length=1)
    description: str | None = None
    tags: list[str] = []
    is_public: bool = False


class CodeSnippetOut(ORMModel):
    id: str
    title: str
    language: str
    code: str
    description: str | None
    tags: list[str]
    is_public: bool
    use_count: int
    created_at: datetime
    updated_at: datetime


# ---- Terminal ----------------------------------------------------------
class TerminalCommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    cwd: str | None = None
    timeout_seconds: int = 30


class TerminalCommandOut(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


# ---- Git ---------------------------------------------------------------
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
    path: str | None
    diff: str


class GitRemoteAction(BaseModel):
    remote: str = "origin"
    branch: str | None = None


# ---- API tester --------------------------------------------------------
class ApiRequestIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    method: str = "GET"
    url: str = Field(min_length=1, max_length=1000)
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    body: str | None = None
    collection: str | None = None


class ApiRequestOut(ORMModel):
    id: str
    name: str
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    body: str | None
    collection: str | None
    created_at: datetime
    updated_at: datetime


class ApiExecIn(BaseModel):
    method: str = "GET"
    url: str = Field(min_length=1, max_length=2000)
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    body: str | None = None
    timeout: int = 20


class ApiExecOut(BaseModel):
    status: int
    headers: dict[str, str]
    body: str
    duration_ms: int
    size_bytes: int
    content_type: str | None = None


# ---- AI codegen helpers ------------------------------------------------
class CodeGenIn(BaseModel):
    prompt: str = Field(min_length=1)
    language: str | None = None
    context_files: list[str] = []
    project_id: str | None = None
    provider: str | None = None  # anthropic|openai|ollama
    model: str | None = None
    api_key_override: str | None = None  # user's BYO key, plaintext one-shot


class CodeGenOut(BaseModel):
    code: str
    explanation: str
    provider: str
    model: str


class CodeReviewIn(BaseModel):
    code: str = Field(min_length=1)
    language: str = "python"
    focus: str | None = None
    provider: str | None = None
    model: str | None = None
    api_key_override: str | None = None


class CodeReviewFinding(BaseModel):
    line: int | None = None
    severity: str = "medium"  # low|medium|high
    category: str = "general"
    message: str
    suggestion: str | None = None


class CodeReviewOut(BaseModel):
    summary: str
    findings: list[CodeReviewFinding] = []
    provider: str
    model: str


class BugFixIn(BaseModel):
    code: str = Field(min_length=1)
    error: str | None = None
    language: str = "python"
    provider: str | None = None
    model: str | None = None
    api_key_override: str | None = None


class BugFixOut(BaseModel):
    fixed_code: str
    explanation: str
    provider: str
    model: str


class ExplainCodeIn(BaseModel):
    code: str = Field(min_length=1)
    language: str = "python"
    provider: str | None = None
    model: str | None = None
    api_key_override: str | None = None


class ExplainCodeOut(BaseModel):
    explanation: str
    provider: str
    model: str


class DocstringIn(BaseModel):
    code: str = Field(min_length=1)
    language: str = "python"
    style: str = "google"  # google|numpy|sphinx|jsdoc
    provider: str | None = None
    api_key_override: str | None = None


class DocstringOut(BaseModel):
    documented_code: str
    provider: str
    model: str


# ---- AI chat for the coding panel --------------------------------------
class CodingChatMessage(BaseModel):
    role: str
    content: str


class CodingChatIn(BaseModel):
    messages: list[CodingChatMessage]
    provider: str | None = None
    model: str | None = None
    project_id: str | None = None
    context_files: list[str] = []
    api_key_override: str | None = None
    max_tokens: int = 2000
    temperature: float = 0.4


class CodingChatOut(BaseModel):
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


# ---- Regex builder -----------------------------------------------------
class RegexExplainBuilderIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=2000)
    flags: str = ""
    provider: str | None = None
    api_key_override: str | None = None


class RegexExplainBuilderOut(BaseModel):
    pattern: str
    flags: str
    explanation: str
    test_cases: list[dict[str, Any]] = []
    provider: str


class RegexTestIn(BaseModel):
    pattern: str
    flags: str = ""
    text: str
    replacement: str | None = None


class RegexMatch(BaseModel):
    match: str
    start: int
    end: int
    groups: list[str] = []


class RegexTestOut(BaseModel):
    matches: list[RegexMatch]
    is_valid: bool
    error: str | None = None
    replaced: str | None = None


class RegexFromDescriptionIn(BaseModel):
    description: str = Field(min_length=1)
    examples_match: list[str] = []
    examples_no_match: list[str] = []
    provider: str | None = None
    api_key_override: str | None = None


class RegexFromDescriptionOut(BaseModel):
    pattern: str
    flags: str
    explanation: str
    provider: str


class RegexLibraryIn(BaseModel):
    title: str
    pattern: str
    flags: str = ""
    description: str | None = None
    explanation: str | None = None


class RegexLibraryOut(ORMModel):
    id: str
    title: str
    pattern: str
    flags: str
    description: str | None
    explanation: str | None
    created_at: datetime


# ---- DB Query builder --------------------------------------------------
class DBQueryIn(BaseModel):
    description: str = Field(min_length=1)
    dialect: str = "postgresql"  # postgresql|mysql|sqlite|mssql
    schema_hint: str | None = None  # paste a CREATE TABLE block as context
    provider: str | None = None
    api_key_override: str | None = None


class DBQueryOut(BaseModel):
    sql: str
    explanation: str
    provider: str


class DBConnectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dialect: str = "sqlite"  # postgresql|mysql|sqlite|mssql
    dsn: str = Field(min_length=1)  # plaintext on input; encrypted at rest


class DBConnectionOut(ORMModel):
    id: str
    name: str
    dialect: str
    created_at: datetime


class DBSchemaTable(BaseModel):
    name: str
    columns: list[dict[str, Any]] = []
    primary_key: list[str] = []
    foreign_keys: list[dict[str, Any]] = []


class DBSchemaOut(BaseModel):
    dialect: str
    tables: list[DBSchemaTable]


class DBExecuteIn(BaseModel):
    connection_id: str
    sql: str = Field(min_length=1)
    limit: int = 200


class DBExecuteOut(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    duration_ms: int
    truncated: bool


# ---- Snippet generator -------------------------------------------------
class SnippetSuggestIn(BaseModel):
    description: str
    language: str = "python"
    provider: str | None = None
    api_key_override: str | None = None


class SnippetSuggestOut(BaseModel):
    title: str
    code: str
    language: str
    description: str
    provider: str
