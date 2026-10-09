"""Top-level API router."""

from fastapi import APIRouter

from compass_api.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
