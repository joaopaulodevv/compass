"""Tests for the operational endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from compass_api import __version__
from compass_api.db.session import get_session


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_does_not_touch_the_database(app: FastAPI, client: TestClient) -> None:
    """Liveness must not fail just because a dependency is down."""

    async def exploding_session() -> AsyncIterator[Any]:
        raise AssertionError("the liveness probe must not open a database session")
        yield  # pragma: no cover

    app.dependency_overrides[get_session] = exploding_session

    assert client.get("/health").status_code == 200


def test_ready_reports_ready_when_the_database_answers(app: FastAPI, client: TestClient) -> None:
    class StubSession:
        async def execute(self, *args: Any, **kwargs: Any) -> None:
            return None

    async def stub_session() -> AsyncIterator[Any]:
        yield StubSession()

    app.dependency_overrides[get_session] = stub_session

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_ready_reports_503_when_the_database_is_unreachable(
    app: FastAPI, client: TestClient
) -> None:
    class BrokenSession:
        async def execute(self, *args: Any, **kwargs: Any) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    async def broken_session() -> AsyncIterator[Any]:
        yield BrokenSession()

    app.dependency_overrides[get_session] = broken_session

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": "error"}}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_openapi_documentation_is_served(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200
