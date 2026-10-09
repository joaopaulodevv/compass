"""Typed application configuration.

Configuration is environment-driven and validated once at startup. Credentials for
capabilities that do not exist yet (LLM provider, vector store, observability vendors)
are declared as optional secrets: they are documented and ready to be wired in, but a
missing value must never prevent the application from starting.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _blank_to_none(value: object) -> object:
    """Treat an empty environment variable as absent.

    `.env.example` declares future credentials with no value, and shells and container
    runtimes happily pass those through as empty strings. An empty credential is not a
    credential, and must not look like one to the code that checks for it.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalSecret = Annotated[SecretStr | None, BeforeValidator(_blank_to_none)]


class AppEnv(StrEnum):
    """Deployment environment the process believes it is running in."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Runtime settings, read from environment variables and an optional `.env` file."""

    # Both candidate paths are checked so that `uv run` works from the repository root
    # and from `apps/api`. In containers the values come from the environment instead.
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application -------------------------------------------------------------
    app_env: AppEnv = AppEnv.LOCAL
    log_level: LogLevel = LogLevel.INFO

    # --- Required infrastructure -------------------------------------------------
    # The only mandatory setting in this phase: the API cannot do anything useful
    # without a database.
    database_url: PostgresDsn
    database_echo: bool = False

    # --- Infrastructure prepared for future use ----------------------------------
    # Redis runs in the local stack but nothing consumes it yet (see docs/architecture.md).
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    # --- Future capabilities (optional on purpose) -------------------------------
    openai_api_key: OptionalSecret = None
    pinecone_api_key: OptionalSecret = None
    langfuse_public_key: OptionalSecret = None
    langfuse_secret_key: OptionalSecret = None
    datadog_api_key: OptionalSecret = None

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are a development affordance, not a production surface."""
        return not self.is_production


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Cached so that validation happens once and so that tests can reset it explicitly
    via `get_settings.cache_clear()`.
    """
    return Settings()
