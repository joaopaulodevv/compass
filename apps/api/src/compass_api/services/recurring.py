"""Detecting charges that repeat every month.

Rule-based and deterministic. "Recurring" is given a precise definition rather than a
vague one, because the answer feeds what the user is told about their committed spending:

* at least `MIN_OCCURRENCES` occurrences,
* an average gap between them of `MIN_INTERVAL_DAYS` to `MAX_INTERVAL_DAYS` - monthly,
  not weekly and not annual,
* amounts within `AMOUNT_TOLERANCE` of their median, so a bill that drifts with usage
  (electricity) still counts while a merchant the user happens to visit at irregular
  amounts does not.

Only expenses are considered, and internal movements are excluded - a monthly transfer
to one's own savings is not a commitment to anyone.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

from compass_api.domain.analysis import Movement, RecurringExpense
from compass_api.domain.money import median_money
from compass_api.services.categorization import normalize

MIN_OCCURRENCES = 3
MIN_INTERVAL_DAYS = 21
MAX_INTERVAL_DAYS = 38

#: How far an individual charge may sit from the median and still count as the same
#: recurring expense. 25% keeps a utility bill that moves with the season.
AMOUNT_TOLERANCE = Decimal("0.25")


def signature_of(movement: Movement) -> str:
    """A stable key for "the same charge again".

    Built from the merchant when the provider supplies one, because a description often
    carries a varying reference number while the merchant does not.
    """
    source = movement.merchant_name or movement.description
    return " ".join(normalize(source))


def detect(movements: Iterable[Movement]) -> tuple[RecurringExpense, ...]:
    """Find monthly recurring expenses, largest median amount first."""
    groups: dict[tuple[uuid.UUID, str], list[Movement]] = defaultdict(list)
    for movement in movements:
        if not movement.is_expense:
            continue
        groups[(movement.account_id, signature_of(movement))].append(movement)

    found = [
        recurring
        for (account_id, signature), group in groups.items()
        if (recurring := _as_recurring(account_id, signature, group)) is not None
    ]
    return tuple(sorted(found, key=lambda item: (-item.median_amount, item.signature)))


def _as_recurring(
    account_id: uuid.UUID, signature: str, group: Sequence[Movement]
) -> RecurringExpense | None:
    if len(group) < MIN_OCCURRENCES:
        return None

    occurrences = sorted(group, key=lambda movement: movement.booked_at)
    average_interval = _average_interval_days([movement.booked_at for movement in occurrences])
    if average_interval is None or not MIN_INTERVAL_DAYS <= average_interval <= MAX_INTERVAL_DAYS:
        return None

    amounts = [-movement.amount for movement in occurrences]
    median = median_money(amounts)
    if not _amounts_are_stable(amounts, median):
        return None

    last_seen = occurrences[-1].booked_at
    return RecurringExpense(
        signature=signature,
        # The most recent description reads better than the oldest if a merchant renamed.
        label=occurrences[-1].merchant_name or occurrences[-1].description,
        category=occurrences[-1].category,
        account_id=account_id,
        occurrences=len(occurrences),
        median_amount=median,
        average_interval_days=average_interval,
        first_seen=occurrences[0].booked_at,
        last_seen=last_seen,
        expected_next=last_seen + timedelta(days=average_interval),
    )


def _average_interval_days(days: Sequence[date]) -> int | None:
    """Mean gap between consecutive occurrences, rounded to whole days."""
    gaps = [(later - earlier).days for earlier, later in pairwise(days)]
    if not gaps:
        return None
    return round(sum(gaps) / len(gaps))


def _amounts_are_stable(amounts: Sequence[Decimal], median: Decimal) -> bool:
    if median <= 0:
        return False
    return all(abs(amount - median) / median <= AMOUNT_TOLERANCE for amount in amounts)
