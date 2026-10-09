"""Calendar arithmetic.

Month arithmetic is where off-by-one bugs live, and every projection depends on it.
"""

from __future__ import annotations

from datetime import date

import pytest

from compass_api.domain.dates import add_months, months_between, with_day


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 15), 1, date(2026, 2, 15)),
        (date(2026, 1, 15), 12, date(2027, 1, 15)),
        (date(2026, 1, 15), 0, date(2026, 1, 15)),
        (date(2026, 3, 15), -3, date(2025, 12, 15)),
        # The day has to survive landing in a shorter month.
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 5, 31), 1, date(2026, 6, 30)),
        (date(2026, 12, 31), 1, date(2027, 1, 31)),
    ],
)
def test_add_months(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected


def test_add_months_does_not_drift_when_stepping_month_by_month() -> None:
    """Stepping twelve single months must land where adding twelve at once does."""
    start = date(2026, 1, 31)
    stepped = start
    for _ in range(12):
        stepped = add_months(stepped, 1)

    assert add_months(start, 12) == date(2027, 1, 31)
    # Stepping clamps at February and keeps the clamped day - a real and intended
    # difference, documented here so nobody "fixes" it by accident.
    assert stepped == date(2027, 1, 28)


@pytest.mark.parametrize(
    ("day", "day_of_month", "expected"),
    [
        (date(2026, 6, 10), 5, date(2026, 6, 5)),
        (date(2026, 6, 10), 30, date(2026, 6, 30)),
        (date(2026, 2, 10), 31, date(2026, 2, 28)),
    ],
)
def test_with_day(day: date, day_of_month: int, expected: date) -> None:
    assert with_day(day, day_of_month) == expected


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 1, 15), date(2026, 7, 15), 6),
        (date(2026, 1, 15), date(2027, 1, 15), 12),
        # A partial month does not count: the money for it has not been set aside yet.
        (date(2026, 1, 15), date(2026, 2, 14), 0),
        (date(2026, 1, 15), date(2026, 2, 16), 1),
        (date(2026, 1, 15), date(2026, 1, 15), 0),
        # A date in the past is zero months away, never negative.
        (date(2026, 7, 15), date(2026, 1, 15), 0),
    ],
)
def test_months_between(start: date, end: date, expected: int) -> None:
    assert months_between(start, end) == expected
