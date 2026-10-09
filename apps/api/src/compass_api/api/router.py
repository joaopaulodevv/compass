"""Top-level API router."""

from fastapi import APIRouter

from compass_api.api.routes import (
    accounts,
    conversations,
    goals,
    health,
    insights,
    knowledge,
    open_finance,
    transactions,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(open_finance.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(insights.router)
api_router.include_router(goals.router)
api_router.include_router(conversations.router)
api_router.include_router(knowledge.router)
