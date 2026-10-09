"""The `X-User-Id` contract.

Authentication does not exist yet, but the isolation key already does: every financial
endpoint requires it, and rejects a request that omits or malforms it before any query
runs. These cases need no database for exactly that reason.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from compass_api.api.deps import USER_ID_HEADER

SCOPED_PATHS = [
    ("GET", "/accounts"),
    ("GET", f"/accounts/{uuid.uuid4()}"),
    ("GET", "/transactions"),
    ("POST", "/open-finance/sync"),
]


@pytest.mark.parametrize(("method", "path"), SCOPED_PATHS)
def test_missing_user_header_is_rejected(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path)

    assert response.status_code == 422
    assert USER_ID_HEADER.lower() in response.text.lower()


@pytest.mark.parametrize(("method", "path"), SCOPED_PATHS)
def test_malformed_user_header_is_rejected(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path, headers={USER_ID_HEADER: "not-a-uuid"})

    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_operational_endpoints_stay_open(client: TestClient, path: str) -> None:
    """Probes must not require a user: an orchestrator has no identity to present."""
    assert client.get(path).status_code != 422


def test_openapi_documents_the_header_as_required(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    parameters = schema["paths"]["/accounts"]["get"]["parameters"]
    header = next(item for item in parameters if item["name"] == USER_ID_HEADER)
    assert header["in"] == "header"
    assert header["required"] is True
