"""Add authentication: user and auth_session tables.

Revision ID: 20260710_0004
Revises: 20260710_0003
Create Date: 2026-07-10 00:00:00.000000

Non-breaking migration. Adds two new tables (user, authsession). No
existing tables are modified. Existing data (prompts, responses,
rubrics, evaluations, pricing) is untouched.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0004"
down_revision: str | None = "20260710_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "authsession",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_authsession_user_id", "authsession", ["user_id"])
    op.create_index("ix_authsession_token", "authsession", ["token"])


def downgrade() -> None:
    op.drop_index("ix_authsession_token", table_name="authsession")
    op.drop_index("ix_authsession_user_id", table_name="authsession")
    op.drop_table("authsession")
    op.drop_table("user")
