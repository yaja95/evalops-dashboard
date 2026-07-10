"""Add model pricing catalog and cost tracking on model responses.

Revision ID: 20260710_0003
Revises: 20260710_0002
Create Date: 2026-07-10 00:00:00.000000

Non-breaking migration. Adds four nullable columns to modelresponse
(provider, input_tokens, output_tokens, cost_usd) and a new model_pricing
table. Existing modelresponse rows are untouched; new columns default to
null, so cost_usd stays unset until a response is created with token
counts and a matching pricing entry exists.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0003"
down_revision: str | None = "20260710_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("modelresponse", sa.Column("provider", sa.String(length=120), nullable=True))
    op.add_column("modelresponse", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("modelresponse", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("modelresponse", sa.Column("cost_usd", sa.Float(), nullable=True))

    op.create_table(
        "modelpricing",
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("input_price_per_1k_tokens", sa.Float(), nullable=False),
        sa.Column("output_price_per_1k_tokens", sa.Float(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model_name"),
    )


def downgrade() -> None:
    op.drop_table("modelpricing")
    op.drop_column("modelresponse", "cost_usd")
    op.drop_column("modelresponse", "output_tokens")
    op.drop_column("modelresponse", "input_tokens")
    op.drop_column("modelresponse", "provider")
