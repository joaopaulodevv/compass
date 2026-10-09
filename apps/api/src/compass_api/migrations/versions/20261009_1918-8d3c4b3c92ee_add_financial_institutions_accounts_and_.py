"""add financial institutions accounts and transactions

Revision ID: 8d3c4b3c92ee
Revises: 45d48e7397c9
Create Date: 2026-10-09 19:18:18.690829

Hand-edited after autogenerate: the enum column rendered its CHECK constraint twice,
once unnamed by the convention and once through it. Only the convention-named one is
kept, so `create_constraint=False` on the column type leaves the explicit constraint as
the single source of that rule.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d3c4b3c92ee"
down_revision: str | Sequence[str] | None = "45d48e7397c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCOUNT_TYPES = ("CHECKING", "SAVINGS", "CREDIT_CARD", "INVESTMENT")


def upgrade() -> None:
    op.create_table(
        "financial_institutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_institutions")),
        sa.UniqueConstraint(
            "provider",
            "external_id",
            name=op.f("uq_financial_institutions_provider_external_id"),
        ),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                *ACCOUNT_TYPES,
                name="account_type",
                native_enum=False,
                create_constraint=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("current_balance", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('CHECKING', 'SAVINGS', 'CREDIT_CARD', 'INVESTMENT')",
            name=op.f("ck_accounts_account_type"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["financial_institutions.id"],
            name=op.f("fk_accounts_institution_id_financial_institutions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "external_id",
            name=op.f("uq_accounts_user_id_provider_external_id"),
        ),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("booked_at", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("merchant_name", sa.String(length=255), nullable=True),
        sa.Column("provider_category", sa.String(length=128), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_transactions_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_transactions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint(
            "account_id",
            "provider",
            "external_id",
            name=op.f("uq_transactions_account_id_provider_external_id"),
        ),
    )
    op.create_index(
        "ix_transactions_user_id_booked_at", "transactions", ["user_id", "booked_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_user_id_booked_at", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("financial_institutions")
