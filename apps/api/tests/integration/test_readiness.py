"""The readiness probe against a real database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_ready_endpoint_reaches_postgresql(api_client: TestClient) -> None:
    response = api_client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}
