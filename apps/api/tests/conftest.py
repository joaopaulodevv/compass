"""Shared test fixtures.

Settings are constructed explicitly rather than read from the developer's environment,
so unit tests are deterministic and never depend on a local `.env`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from compass_api.core.config import AppEnv, Settings
from compass_api.main import create_app

# A reachable database is only required by the integration suite; unit tests merely need
# a syntactically valid URL.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://compass:compass@localhost:5432/compass",
)


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env=AppEnv.TEST, database_url=TEST_DATABASE_URL)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """HTTP client that also exercises the application lifespan."""
    with TestClient(app) as test_client:
        yield test_client
