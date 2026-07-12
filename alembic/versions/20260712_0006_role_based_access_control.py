"""Add role-based access control: role column on user.

Revision ID: 20260712_0006
Revises: 20260712_0005
Create Date: 2026-07-12 00:00:00.000000

Non-breaking migration. Adds one new column (role) to the existing
user table, defaulting existing and new rows to "member". The seeded
demo account is promoted to "admin" so it keeps working after
upgrade without needing a fresh re-seed.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712_0006"
down_revision: str | None = "20260712_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
    )
    op.execute("UPDATE \"user\" SET role = 'admin' WHERE username = 'demo'")


def downgrade() -> None:
    op.drop_column("user", "role")
