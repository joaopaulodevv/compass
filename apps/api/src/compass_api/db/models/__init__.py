"""ORM models.

Every model must be imported here: Alembic autogenerate only sees what is attached to
`Base.metadata` at import time.
"""

from compass_api.db.models.account import Account
from compass_api.db.models.conversation import Conversation, ConversationMessage
from compass_api.db.models.financial_goal import FinancialGoal
from compass_api.db.models.financial_institution import FinancialInstitution
from compass_api.db.models.transaction import Transaction
from compass_api.db.models.user import User

__all__ = [
    "Account",
    "Conversation",
    "ConversationMessage",
    "FinancialGoal",
    "FinancialInstitution",
    "Transaction",
    "User",
]
