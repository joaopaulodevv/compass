"""Operational endpoints.

Two distinct questions, deliberately kept separate:

* `GET /health`  - liveness. Is the process up? No dependencies are touched, so an
  orchestrator never restarts a healthy process because Postgres hiccuped.
* `GET /ready`   - readiness. Can this instance serve traffic? Checks the database.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from compass_api import __version__
from compass_api.api.deps import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = Field(default=__version__)


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["ok", "error"]]


@router.get("/health", summary="Liveness probe")
async def health() -> HealthResponse:
    """Return `ok` whenever the process is able to serve requests."""
    return HealthResponse()


@router.get(
    "/ready",
    summary="Readiness probe",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready(session: SessionDep, response: Response) -> ReadinessResponse:
    """Verify that this instance can reach its required dependencies."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        # Log the failure without echoing connection details back to the caller.
        logger.exception("readiness check failed", extra={"check": "database"})
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", checks={"database": "error"})

    return ReadinessResponse(status="ready", checks={"database": "ok"})
