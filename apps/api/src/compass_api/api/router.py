"""Top-level API router."""

from fastapi import APIRouter

from compass_api.api.routes import accounts, health, insights, open_finance, transactions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(open_finance.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(insights.router)
