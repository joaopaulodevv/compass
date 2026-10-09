"""Triggering ingestion from the Open Finance provider.

Synchronous today because the sandbox provider answers instantly. Against a real
provider this becomes a queued job and the endpoint returns 202 with a job id - which is
the first concrete use for the Redis already in the stack.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from compass_api.api.deps import CurrentUserId, OpenFinanceProviderDep, SessionDep
from compass_api.services.open_finance_sync import (
    DEFAULT_WINDOW_DAYS,
    OpenFinanceSyncService,
    SyncReport,
    UnknownUserError,
)

router = APIRouter(prefix="/open-finance", tags=["open finance"])


class SyncRequest(BaseModel):
    """The window to ingest. Both ends optional; the service picks sensible defaults."""

    since: date | None = Field(
        default=None,
        description=(
            f"Earliest booking date. Defaults to {DEFAULT_WINDOW_DAYS} days before `until`."
        ),
    )
    until: date | None = Field(default=None, description="Latest booking date. Defaults to today.")

    @model_validator(mode="after")
    def check_window(self) -> SyncRequest:
        if self.since and self.until and self.since > self.until:
            raise ValueError("since must not be later than until")
        return self


class SyncResponse(BaseModel):
    """Counts describing what the sync did - never the financial data itself."""

    provider: str
    user_id: UUID
    since: date
    until: date
    institutions: int
    accounts: int
    accounts_created: int
    transactions: int
    transactions_created: int
    transactions_updated: int

    @classmethod
    def of(cls, report: SyncReport) -> SyncResponse:
        return cls(
            provider=report.provider,
            user_id=report.user_id,
            since=report.since,
            until=report.until,
            institutions=report.institutions,
            accounts=report.accounts,
            accounts_created=report.accounts_created,
            transactions=report.transactions,
            transactions_created=report.transactions_created,
            transactions_updated=report.transactions_updated,
        )


@router.post(
    "/sync",
    summary="Ingest accounts and transactions for the acting user",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No such user"}},
)
async def sync(
    user_id: CurrentUserId,
    session: SessionDep,
    provider: OpenFinanceProviderDep,
    request: SyncRequest | None = None,
) -> SyncResponse:
    """Re-reading an overlapping window is safe: ingestion is idempotent."""
    window = request or SyncRequest()
    service = OpenFinanceSyncService(session, provider)
    try:
        report = await service.sync_user(user_id, since=window.since, until=window.until)
    except UnknownUserError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        ) from error
    return SyncResponse.of(report)
