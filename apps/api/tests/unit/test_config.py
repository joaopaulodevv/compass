"""Tests for the configuration layer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compass_api.core.config import AppEnv, Settings


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "database_url" in str(exc_info.value)


def test_future_credentials_are_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing LLM/vector-store/observability key must not block startup."""
    for name in (
        "OPENAI_API_KEY",
        "PINECONE_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "DATADOG_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
    )

    assert settings.openai_api_key is None
    assert settings.pinecone_api_key is None
    assert settings.langfuse_public_key is None
    assert settings.langfuse_secret_key is None
    assert settings.datadog_api_key is None


def test_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/compass")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")

    settings = Settings(_env_file=None)

    assert settings.app_env is AppEnv.PRODUCTION
    assert settings.is_production is True
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-not-a-real-key"


def test_secrets_are_not_exposed_by_repr() -> None:
    """Financial-grade hygiene: credentials must not leak through logs or tracebacks."""
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        openai_api_key="sk-not-a-real-key",
        datadog_api_key="dd-not-a-real-key",
    )

    rendered = f"{settings!r} {settings!s}"

    assert "sk-not-a-real-key" not in rendered
    assert "dd-not-a-real-key" not in rendered


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [(AppEnv.LOCAL, True), (AppEnv.TEST, True), (AppEnv.STAGING, True), (AppEnv.PRODUCTION, False)],
)
def test_docs_are_disabled_only_in_production(app_env: AppEnv, expected: bool) -> None:
    settings = Settings(
        _env_file=None,
        app_env=app_env,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
    )

    assert settings.docs_enabled is expected


def test_blank_credentials_are_treated_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.env.example` ships future keys empty; empty must not read as configured."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("PINECONE_API_KEY", "   ")

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
    )

    assert settings.openai_api_key is None
    assert settings.pinecone_api_key is None
