"""Expense categories and the economic role of a movement.

Two different questions are answered here, and keeping them apart is what makes the
cash-flow numbers correct:

1. *What was this money spent on?* - the category (housing, groceries, ...).
2. *Did money actually enter or leave the user's finances?* - the role.

The second question exists because a statement contains movements that are not income
or expense at all. Moving R$ 800 from checking to savings is not spending, and paying
the credit-card bill is not either - the spending already happened when the card was
used. Counting both the bill payment and the card purchases would inflate every expense
figure derived from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExpenseCategory(StrEnum):
    """What a movement was for.

    Coarse on purpose: a taxonomy the user can reason about, not a provider's product
    tree. `OTHER` is a real answer - it is better than a confident wrong label.
    """

    # Income
    INCOME = "INCOME"
    INVESTMENT_INCOME = "INVESTMENT_INCOME"

    # Internal movements (neither income nor expense)
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    CREDIT_CARD_PAYMENT = "CREDIT_CARD_PAYMENT"

    # Expenses
    HOUSING = "HOUSING"
    UTILITIES = "UTILITIES"
    GROCERIES = "GROCERIES"
    DINING = "DINING"
    TRANSPORT = "TRANSPORT"
    HEALTH = "HEALTH"
    EDUCATION = "EDUCATION"
    SUBSCRIPTIONS = "SUBSCRIPTIONS"
    SHOPPING = "SHOPPING"
    FEES = "FEES"

    OTHER = "OTHER"


#: Movements that shuffle money the user already has. Excluded from income and expenses
#: so that nothing is counted twice.
INTERNAL_CATEGORIES = frozenset(
    {ExpenseCategory.INTERNAL_TRANSFER, ExpenseCategory.CREDIT_CARD_PAYMENT}
)


def is_internal(category: ExpenseCategory) -> bool:
    """Whether this movement only moves money between the user's own balances."""
    return category in INTERNAL_CATEGORIES


@dataclass(frozen=True, slots=True)
class Categorization:
    """A category together with what decided it, so the result can be audited."""

    category: ExpenseCategory
    #: `keyword:groceries`, `provider:utilities`, `sign:credit` or `fallback`.
    rule: str
