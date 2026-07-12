"""Add login rate limiting: loginattempt table.

Revision ID: 20260712_0005
Revises: 20260710_0004
Create Date: 2026-07-12 00:00:00.000000

Non-breaking migration. Adds one new table (loginattempt). No existing
tables are modified. Existing data is untouched.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712_0005"
down_revision: str | None = "20260710_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "loginattempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loginattempt_username", "loginattempt", ["username"])


def downgrade() -> None:
    op.drop_index("ix_loginattempt_username", table_name="loginattempt")
    op.drop_table("loginattempt")
