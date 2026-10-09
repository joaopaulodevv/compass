"""Tests for application bootstrap."""

from __future__ import annotations

from fastapi.testclient import TestClient

from compass_api import __version__
from compass_api.core.config import AppEnv, Settings
from compass_api.main import create_app


def test_app_metadata(settings: Settings) -> None:
    app = create_app(settings)

    assert app.title == "Compass API"
    assert app.version == __version__


def test_lifespan_starts_and_stops_without_infrastructure(settings: Settings) -> None:
    """The process must boot without opening a database connection."""
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200


def test_openapi_schema_documents_every_route(settings: Settings) -> None:
    schema = create_app(settings).openapi()

    assert set(schema["paths"]) == {
        "/health",
        "/ready",
        "/open-finance/sync",
        "/accounts",
        "/accounts/{account_id}",
        "/transactions",
        "/insights/cashflow",
        "/insights/recurring-expenses",
        "/insights/saving-capacity",
    }


def test_documentation_endpoints_are_disabled_in_production() -> None:
    production = Settings(
        _env_file=None,
        app_env=AppEnv.PRODUCTION,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
    )

    client = TestClient(create_app(production))

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/health").status_code == 200
