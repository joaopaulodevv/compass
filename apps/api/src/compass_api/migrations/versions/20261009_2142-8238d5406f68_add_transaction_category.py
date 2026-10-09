"""add transaction category

Revision ID: 8238d5406f68
Revises: 8d3c4b3c92ee
Create Date: 2026-10-09 21:42:07.904621

Existing rows get `OTHER`. They are not back-filled here on purpose: the categorisation
rules live in application code, and a data migration that imported them would freeze one
version of those rules into the schema history. Re-running a sync re-categorises
everything, because the upsert refreshes the column.

Hand-edited after autogenerate so the CHECK constraint carries the project's naming
convention, matching `ck_accounts_account_type`.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8238d5406f68"
down_revision: str | Sequence[str] | None = "8d3c4b3c92ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXPENSE_CATEGORIES = (
    "INCOME",
    "INVESTMENT_INCOME",
    "INTERNAL_TRANSFER",
    "CREDIT_CARD_PAYMENT",
    "HOUSING",
    "UTILITIES",
    "GROCERIES",
    "DINING",
    "TRANSPORT",
    "HEALTH",
    "EDUCATION",
    "SUBSCRIPTIONS",
    "SHOPPING",
    "FEES",
    "OTHER",
)

# Bare name: `op.create_check_constraint` applies the project's naming convention, so
# passing the full name would yield `ck_transactions_ck_transactions_expense_category`.
CONSTRAINT_NAME = "expense_category"
FINAL_CONSTRAINT_NAME = "ck_transactions_expense_category"


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "category",
            sa.Enum(
                *EXPENSE_CATEGORIES,
                name="expense_category",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="OTHER",
            nullable=False,
        ),
    )
    op.add_column("transactions", sa.Column("category_rule", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "transactions",
        "category IN ({})".format(", ".join(f"'{value}'" for value in EXPENSE_CATEGORIES)),
    )


def downgrade() -> None:
    op.drop_constraint(FINAL_CONSTRAINT_NAME, "transactions", type_="check")
    op.drop_column("transactions", "category_rule")
    op.drop_column("transactions", "category")
