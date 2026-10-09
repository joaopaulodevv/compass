"""Request validation and response mapping for the sync endpoint."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from compass_api.api.routes.open_finance import SyncRequest, SyncResponse
from compass_api.services.open_finance_sync import SyncReport


def test_window_may_be_omitted_entirely() -> None:
    request = SyncRequest()

    assert request.since is None
    assert request.until is None


def test_inverted_window_is_rejected_before_any_work_happens() -> None:
    with pytest.raises(ValidationError, match="since"):
        SyncRequest(since=date(2026, 6, 1), until=date(2026, 5, 1))


def test_single_day_window_is_accepted() -> None:
    day = date(2026, 6, 1)

    request = SyncRequest(since=day, until=day)

    assert request.since == request.until == day


def test_report_derives_how_many_rows_were_refreshed() -> None:
    report = SyncReport(
        provider="mock",
        user_id=uuid.uuid4(),
        since=date(2026, 1, 1),
        until=date(2026, 6, 30),
        institutions=2,
        accounts=3,
        accounts_created=0,
        transactions=104,
        transactions_created=4,
    )

    assert report.transactions_updated == 100

    response = SyncResponse.of(report)
    assert response.transactions_updated == 100
    assert response.transactions_created == 4
    assert response.provider == "mock"
