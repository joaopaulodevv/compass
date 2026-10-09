"""add financial goals

Revision ID: 9678715d3147
Revises: 8238d5406f68
Create Date: 2026-10-09 22:10:00.000000

Hand-edited after autogenerate, which emitted the status enum's CHECK constraint twice -
once unnamed by the convention and once through it. Only the convention-named one is
kept.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9678715d3147"
down_revision: str | Sequence[str] | None = "8238d5406f68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GOAL_STATUSES = ("ACTIVE", "ACHIEVED", "ARCHIVED")


def upgrade() -> None:
    op.create_table(
        "financial_goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("initial_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("current_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("monthly_contribution", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *GOAL_STATUSES,
                name="goal_status",
                native_enum=False,
                create_constraint=False,
                length=16,
            ),
            nullable=False,
        ),
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
            "status IN ('ACTIVE', 'ACHIEVED', 'ARCHIVED')",
            name=op.f("ck_financial_goals_goal_status"),
        ),
        sa.CheckConstraint(
            "current_amount >= 0 AND initial_amount >= 0",
            name=op.f("ck_financial_goals_amounts_not_negative"),
        ),
        sa.CheckConstraint(
            "monthly_contribution IS NULL OR monthly_contribution >= 0",
            name=op.f("ck_financial_goals_contribution_not_negative"),
        ),
        sa.CheckConstraint(
            "target_amount > 0", name=op.f("ck_financial_goals_target_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_financial_goals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_goals")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_financial_goals_user_id_name")),
    )
    op.create_index("ix_financial_goals_user_id", "financial_goals", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_financial_goals_user_id", table_name="financial_goals")
    op.drop_table("financial_goals")
