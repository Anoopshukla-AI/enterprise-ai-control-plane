"""
Application configuration — loaded from environment variables via Pydantic Settings.
All secrets must live in .env or be injected by docker-compose / CI.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME: str = "Enterprise AI Control Plane"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # development | production
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str  # REQUIRED — set in .env
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str  # REQUIRED — postgresql+asyncpg://user:pass@host/db

    # ------------------------------------------------------------------
    # LLM Providers
    # ------------------------------------------------------------------
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_DEFAULT_MODEL: str = "llama3"

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------
    POLICY_FILE: Path = Path("config/policy.yaml")

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------
    ADMIN_API_KEY: str = ""  # Simple admin dashboard auth key

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance. Import this everywhere."""
    return Settings()  # type: ignore[call-arg]


# Convenience singleton — import as `from app.config import settings`
settings: Settings = get_settings()
