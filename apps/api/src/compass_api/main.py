"""Application entrypoint and composition root."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from compass_api import __version__
from compass_api.api.router import api_router
from compass_api.core.config import Settings, get_settings
from compass_api.core.logging import configure_logging
from compass_api.db.session import dispose_engine

logger = logging.getLogger(__name__)

DESCRIPTION = """
Compass is an AI-powered personal financial assistant.

This API is in early development. Only operational endpoints are implemented today;
see the repository roadmap for what is planned.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the lifecycle of process-wide resources."""
    settings: Settings = app.state.settings
    logger.info("application starting", extra={"app_env": settings.app_env.value})
    yield
    await dispose_engine()
    logger.info("application stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    A factory (rather than a module-level singleton) keeps settings injectable, which is
    what makes the app testable without touching the real environment.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Compass API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.include_router(api_router)
    return app


app = create_app()
