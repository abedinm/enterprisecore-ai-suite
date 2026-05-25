"""Central application configuration loaded from environment / .env file."""
from __future__ import annotations

import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Path layout
# ---------------------------------------------------------------------------
# BACKEND_ROOT — where the code lives (for finding .env, source files).
# DATA_ROOT    — where USER DATA goes (DB, uploads, logs, knowledge). MUST
#                persist across launches. In a PyInstaller-frozen .exe the
#                code lives in a temp _MEIxxxx directory that's wiped every
#                run, so we can't store data there.
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


def _resolve_data_root() -> Path:
    """Pick a stable, writable directory for user data.

    Priority:
      1. ``ENTERPRISECORE_DATA_DIR`` env var (Electron sets this to the per-
         user data path; tests use it too).
      2. Frozen build → platform-appropriate user data dir
         (``%LOCALAPPDATA%\\EnterpriseCore AI Suite`` on Windows,
         ``~/.enterprisecore`` on Linux/macOS).
      3. Dev build → the in-repo ``backend/`` directory (current behaviour).
    """
    override = os.environ.get("ENTERPRISECORE_DATA_DIR")
    if override:
        p = Path(override).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    if getattr(sys, "frozen", False):
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            p = Path(base) / "EnterpriseCore AI Suite"
        else:
            p = Path.home() / ".enterprisecore"
        p.mkdir(parents=True, exist_ok=True)
        return p

    return BACKEND_ROOT


DATA_ROOT = _resolve_data_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "EnterpriseCore AI Suite"
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = True
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    # Public-facing URL of the SPA — used to build magic-link / verification
    # URLs that point at the HashRouter (``<base>/#/auth/consume?token=...``)
    # instead of the JSON API. Override in production to ``https://app.your-
    # company.com`` (no trailing slash, no path).
    app_base_url: str = "http://127.0.0.1:8765"

    db_backend: Literal["sqlite", "postgres"] = "sqlite"
    sqlite_path: str = "storage/enterprisecore.db"
    postgres_dsn: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/enterprisecore"

    # SECRET_KEY footgun: previously `default_factory=secrets.token_urlsafe(64)`
    # silently re-rolled the key on every process start. In dev that's tolerable
    # (you get logged out on reload); in prod it invalidates every active session
    # AND breaks Fernet decrypt of every encrypted column. So the default is now
    # the empty string and the validator below refuses to boot any non-dev env
    # without an explicit SECRET_KEY. Dev still gets a process-local random key
    # — but it's marked obviously ephemeral.
    secret_key: str = ""
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 14
    password_min_length: int = 10
    encryption_key: str = ""
    # Refuse to boot a multi-tenant production deploy on SQLite unless the
    # operator explicitly opts in (single-tenant on-prem desktop deploys are
    # fine, hence the override). SQLite cannot serve concurrent writers across
    # multiple uvicorn workers and lacks the isolation guarantees auditors
    # expect.
    allow_sqlite_in_prod: bool = False

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_host: str = "http://127.0.0.1:11434"
    ai_default_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    # Hard ceiling on each user's paid-AI spending in any rolling 24-hour
    # window. Ollama (local) is exempt. 0 disables the limit.
    ai_daily_usd_limit_per_user: float = 5.0

    # Knowledge Hub
    knowledge_storage_dir: str = "storage/knowledge"
    knowledge_default_embedding_provider: Literal["ollama", "openai"] = "ollama"
    knowledge_default_embedding_model: str = "nomic-embed-text"
    knowledge_ingest_poll_seconds: int = 5
    knowledge_max_upload_mb: int = 100
    knowledge_url_fetch_timeout: int = 30

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,app://./"

    license_key: str = ""
    license_api_url: str = "https://ec-license-server.fly.dev/api/v1/licenses"
    license_offline_grace_days: int = 7

    default_currency: str = "USD"
    default_locale: str = "en"
    default_timezone: str = "UTC"

    @computed_field  # type: ignore[misc]
    @property
    def sqlalchemy_url(self) -> str:
        if self.db_backend == "postgres":
            return self.postgres_dsn
        # SQLite file always lives under DATA_ROOT so it survives PyInstaller
        # temp-dir wipes on every launch of the packaged .exe.
        sqlite_file = DATA_ROOT / self.sqlite_path
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{sqlite_file.as_posix()}"

    @computed_field  # type: ignore[misc]
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def storage_dir(self) -> Path:
        # All user files (uploads, marketing media, knowledge ingest, logs)
        # live under DATA_ROOT — never inside the PyInstaller temp dir.
        d = DATA_ROOT / "storage"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @computed_field  # type: ignore[misc]
    @property
    def data_root(self) -> Path:
        """The persistent user-data directory (read-only convenience accessor)."""
        return DATA_ROOT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    _validate_runtime_env(s)
    return s


def _validate_runtime_env(s: Settings) -> None:
    """Hard-fail boot if the operator has forgotten a security-critical knob.

    Dev gets ergonomic auto-defaults; staging/production must be configured.
    The goal is to catch misconfigurations BEFORE the first request, not
    after the first session-invalidation incident.
    """
    if s.app_env == "development":
        if not s.secret_key:
            # Stable per-process random key — at least sessions don't break
            # within a single dev run. Marked obviously ephemeral in logs.
            object.__setattr__(s, "secret_key", "dev-ephemeral-" + secrets.token_urlsafe(48))
        return

    problems: list[str] = []
    if not s.secret_key or s.secret_key.startswith("dev-ephemeral-"):
        problems.append(
            "SECRET_KEY is required in non-development environments. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    if not s.encryption_key:
        problems.append(
            "ENCRYPTION_KEY is required in non-development environments. "
            "Without it, encrypted columns derive their key from SECRET_KEY; "
            "rotation becomes impossible. Generate with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    if s.db_backend == "sqlite" and not s.allow_sqlite_in_prod:
        problems.append(
            f"db_backend=sqlite is not allowed when app_env={s.app_env!r}. "
            "SQLite cannot serve concurrent writers across uvicorn workers. "
            "Set db_backend=postgres OR set allow_sqlite_in_prod=true if this "
            "is a single-tenant on-prem desktop deploy (you accept the risk)."
        )
    # CORS sanity — `*` plus credentialed cookies is a known footgun.
    origins = s.cors_origin_list
    if "*" in origins:
        problems.append(
            "cors_origins contains '*' which is incompatible with "
            "credentialed cookies. List concrete origins instead."
        )
    if problems:
        joined = "\n  - ".join(problems)
        raise RuntimeError(
            f"Refusing to start {s.app_name} in {s.app_env!r}:\n  - {joined}"
        )


settings = get_settings()
