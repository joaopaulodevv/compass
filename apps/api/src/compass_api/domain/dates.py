"""Calendar arithmetic used by the financial engine.

Month arithmetic is not day arithmetic: "one month after 31 January" has to land on a day
that exists, and projections that step month by month must not drift. These helpers are
here so that logic exists once.
"""

from __future__ import annotations

import calendar
from datetime import date


def add_months(day: date, months: int) -> date:
    """Shift by whole months, clamping the day to the length of the target month.

    `add_months(date(2026, 1, 31), 1)` is 28 February 2026, not 3 March.
    """
    month_index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(month_index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def with_day(day: date, day_of_month: int) -> date:
    """Set the day of the month, clamped to the length of that month.

    `with_day(date(2026, 2, 10), 31)` is 28 February 2026.
    """
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=min(day_of_month, last_day))


def months_between(start: date, end: date) -> int:
    """Whole months from `start` to `end`, never negative.

    A partial month does not count: from 10 January to 9 February is zero whole months,
    because the money for that month has not been put aside yet.
    """
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)
