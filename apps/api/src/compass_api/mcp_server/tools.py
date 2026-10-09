"""The financial tools, as thin as a tool should be.

Each one parses its arguments, opens a session, calls a service, and serialises the
result. There is no financial rule in this file and there must never be: the same
functions back the HTTP API, so a rule added here would exist in one transport and not
the other (ADR-0004).

Every tool takes `user_id` explicitly. Authentication does not exist yet, so the caller
supplies it - the same stand-in the HTTP layer uses as a header. When authentication
arrives, the agent will carry a verified identity and this argument disappears.

A tool that cannot answer raises `ToolError`, whose message reaches the model - the SDK
hides the detail of any other exception behind a generic failure. That distinction is the
point: a goal that does not exist must come back as "goal not found", not as a
plausible-looking zero and not as an opaque crash.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import date
from decimal import Decimal
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from compass_api.db.session import get_sessionmaker
from compass_api.domain.goals import GoalPathOption, GoalTerms
from compass_api.mcp_server.serialization import to_jsonable
from compass_api.repositories.accounts import AccountRepository
from compass_api.repositories.transactions import TransactionRepository
from compass_api.services.goals import GoalService
from compass_api.services.insights import AnalysisWindow, InsightsService

DEFAULT_TRANSACTION_LIMIT = 50
MAX_TRANSACTION_LIMIT = 200


#: The dependency-injection seam for a transport that has none. FastAPI has
#: `dependency_overrides`; MCP tools are plain functions whose signature is their public
#: schema, so a session factory cannot be passed as an argument. Tests set this; the
#: server never does.
sessionmaker_override: ContextVar[async_sessionmaker[AsyncSession] | None] = ContextVar(
    "compass_mcp_sessionmaker", default=None
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    maker = sessionmaker_override.get() or get_sessionmaker()
    async with maker() as session:
        yield session


def _user(user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(user_id)
    except ValueError as error:
        raise ToolError(f"user_id is not a valid UUID: {user_id!r}") from error


def _goal_id(goal_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(goal_id)
    except ValueError as error:
        raise ToolError(f"goal_id is not a valid UUID: {goal_id!r}") from error


def _window(since: str | None, until: str | None) -> AnalysisWindow:
    return AnalysisWindow.resolve(
        date.fromisoformat(since) if since else None,
        date.fromisoformat(until) if until else None,
    )


async def get_accounts(user_id: str) -> dict[str, Any]:
    """List the user's accounts with the balance each institution last reported."""
    async with session_scope() as session:
        accounts = await AccountRepository(session).list_for_user(_user(user_id))
        return {
            "accounts": [
                {
                    "id": str(account.id),
                    "institution": account.institution.name,
                    "type": account.type.value,
                    "name": account.name,
                    "currency": account.currency,
                    "current_balance": str(account.current_balance),
                    "synced_at": account.synced_at.isoformat(),
                }
                for account in accounts
            ]
        }


async def get_transactions(
    user_id: str,
    since: str | None = None,
    until: str | None = None,
    account_id: str | None = None,
    limit: int = DEFAULT_TRANSACTION_LIMIT,
) -> dict[str, Any]:
    """List the user's transactions, most recent first.

    Amounts are signed: negative is money leaving the account.
    """
    window = _window(since, until)
    async with session_scope() as session:
        repository = TransactionRepository(session)
        rows = await repository.list_for_user(
            _user(user_id),
            account_id=uuid.UUID(account_id) if account_id else None,
            since=window.since,
            until=window.until,
            limit=min(limit, MAX_TRANSACTION_LIMIT),
        )
        total = await repository.count_for_user(
            _user(user_id),
            account_id=uuid.UUID(account_id) if account_id else None,
            since=window.since,
            until=window.until,
        )
    return {
        "since": window.since.isoformat(),
        "until": window.until.isoformat(),
        "total": total,
        "transactions": [
            {
                "id": str(row.id),
                "account_id": str(row.account_id),
                "booked_at": row.booked_at.isoformat(),
                "amount": str(row.amount),
                "currency": row.currency,
                "description": row.description,
                "merchant_name": row.merchant_name,
                "category": row.category.value,
            }
            for row in rows
        ],
    }


async def get_cashflow(
    user_id: str, since: str | None = None, until: str | None = None
) -> dict[str, Any]:
    """Income, expenses, net and the monthly series over a window.

    Credit-card bill payments and transfers between the user's own accounts are excluded
    from income and expenses - the card's spending is already counted where it happened.
    The excluded total is reported as `internal_movements`.
    """
    window = _window(since, until)
    async with session_scope() as session:
        summary = await InsightsService(session).cashflow(_user(user_id), window)
    payload: dict[str, Any] = to_jsonable(summary)
    return payload


async def detect_recurring_expenses(
    user_id: str, since: str | None = None, until: str | None = None
) -> dict[str, Any]:
    """Charges that repeat monthly: at least three occurrences, a 21-38 day cadence, and
    amounts within 25% of their median."""
    window = _window(since, until)
    async with session_scope() as session:
        found = await InsightsService(session).recurring_expenses(_user(user_id), window)
    return {
        "since": window.since.isoformat(),
        "until": window.until.isoformat(),
        "monthly_total": str(sum((item.median_amount for item in found), Decimal("0.00"))),
        "recurring_expenses": to_jsonable(found),
    }


async def calculate_saving_capacity(
    user_id: str, since: str | None = None, until: str | None = None
) -> dict[str, Any]:
    """How much the user could put aside monthly: the median monthly net over whole
    calendar months, floored at zero.

    `months_considered` of 0 means there is not enough history to answer - not that the
    capacity is zero.
    """
    window = _window(since, until)
    async with session_scope() as session:
        capacity = await InsightsService(session).saving_capacity(_user(user_id), window)
    payload: dict[str, Any] = to_jsonable(capacity)
    return payload


async def list_goals(user_id: str) -> dict[str, Any]:
    """The user's financial goals and their stored terms."""
    async with session_scope() as session:
        goals = await GoalService(session).list(_user(user_id))
    return {
        "goals": [
            {
                "id": str(goal.id),
                "name": goal.name,
                "target_amount": str(goal.target_amount),
                "target_date": goal.target_date.isoformat() if goal.target_date else None,
                "current_amount": str(goal.current_amount),
                "monthly_contribution": (
                    str(goal.monthly_contribution)
                    if goal.monthly_contribution is not None
                    else None
                ),
                "status": goal.status.value,
            }
            for goal in goals
        ]
    }


async def simulate_goal(
    user_id: str,
    target_amount: str,
    target_date: str | None = None,
    current_amount: str = "0.00",
    monthly_contribution: str | None = None,
    annual_return_rate: str = "0",
) -> dict[str, Any]:
    """Project a goal that need not exist yet: how long it takes, and the gap if dated.

    Omit `monthly_contribution` to use the saving capacity measured from the user's own
    history. `annual_return_rate` is the caller's assumption as a fraction (0.11 for 11%
    a year); Compass does not know what any product pays.
    """
    terms = GoalTerms(
        target_amount=Decimal(target_amount),
        current_amount=Decimal(current_amount),
        started_on=date.today(),
        target_date=date.fromisoformat(target_date) if target_date else None,
        initial_amount=Decimal(current_amount),
    )
    async with session_scope() as session:
        contribution, source, simulation, gap = await GoalService(session).simulate_draft(
            _user(user_id),
            terms,
            monthly_contribution=(
                Decimal(monthly_contribution) if monthly_contribution is not None else None
            ),
            annual_return_rate=Decimal(annual_return_rate),
        )
    return {
        "monthly_contribution": str(contribution),
        "contribution_source": source.value,
        "simulation": to_jsonable(simulation),
        "gap": to_jsonable(gap),
    }


async def calculate_goal_gap(
    user_id: str,
    goal_id: str,
    monthly_contribution: str | None = None,
    annual_return_rate: str = "0",
) -> dict[str, Any]:
    """What an existing goal's deadline demands, and what is missing.

    Also returns the projection and the progress against the straight line to the target
    date, since they come from the same reading of the goal.
    """
    async with session_scope() as session:
        service = GoalService(session)
        goal = await service.get(_user(user_id), _goal_id(goal_id))
        if goal is None:
            raise ToolError("goal not found")
        forecast = await service.forecast(
            _user(user_id),
            goal,
            monthly_contribution=(
                Decimal(monthly_contribution) if monthly_contribution is not None else None
            ),
            annual_return_rate=Decimal(annual_return_rate),
        )
    return {
        "goal_id": str(goal.id),
        "goal_name": goal.name,
        "monthly_contribution": str(forecast.monthly_contribution),
        "contribution_source": forecast.contribution_source.value,
        "simulation": to_jsonable(forecast.simulation),
        "gap": to_jsonable(forecast.gap),
        "progress": to_jsonable(forecast.progress),
    }


async def compare_goal_paths(
    user_id: str, goal_id: str, options: list[dict[str, str]]
) -> dict[str, Any]:
    """Compare contribution-and-return scenarios for a goal.

    Each option is `{"label": ..., "monthly_contribution": "900.00",
    "annual_return_rate": "0.11"}`. Results come back soonest first, unreachable last.
    """
    parsed = [
        GoalPathOption(
            label=str(option["label"]),
            monthly_contribution=Decimal(option["monthly_contribution"]),
            annual_return_rate=Decimal(option.get("annual_return_rate", "0")),
        )
        for option in options
    ]
    async with session_scope() as session:
        service = GoalService(session)
        goal = await service.get(_user(user_id), _goal_id(goal_id))
        if goal is None:
            raise ToolError("goal not found")
        paths = await service.compare(goal, parsed)
    return {"goal_id": str(goal.id), "paths": to_jsonable(paths)}


#: Every tool the server exposes. One list, so the server, the agent and the tests all
#: agree on what exists.
FINANCIAL_TOOLS = (
    get_accounts,
    get_transactions,
    get_cashflow,
    detect_recurring_expenses,
    calculate_saving_capacity,
    list_goals,
    simulate_goal,
    calculate_goal_gap,
    compare_goal_paths,
)
