"""Central application configuration loaded from environment / .env file."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


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

    db_backend: Literal["sqlite", "postgres"] = "sqlite"
    sqlite_path: str = "storage/enterprisecore.db"
    postgres_dsn: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/enterprisecore"

    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 14
    password_min_length: int = 10
    encryption_key: str = ""

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_host: str = "http://127.0.0.1:11434"
    ai_default_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,app://./"

    license_key: str = ""

    default_currency: str = "USD"
    default_locale: str = "en"
    default_timezone: str = "UTC"

    @computed_field  # type: ignore[misc]
    @property
    def sqlalchemy_url(self) -> str:
        if self.db_backend == "postgres":
            return self.postgres_dsn
        sqlite_file = BACKEND_ROOT / self.sqlite_path
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{sqlite_file.as_posix()}"

    @computed_field  # type: ignore[misc]
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def storage_dir(self) -> Path:
        d = BACKEND_ROOT / "storage"
        d.mkdir(parents=True, exist_ok=True)
        return d


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
