"""Add LLM judge cost tracking on evaluations.

Revision ID: 20260712_0007
Revises: 20260712_0006
Create Date: 2026-07-12 00:00:00.000000

Non-breaking migration. Adds four nullable columns to evaluation
(judge_input_tokens, judge_output_tokens, judge_model, judge_cost_usd).
Existing evaluation rows are untouched; new columns default to null, so
judge_cost_usd stays unset until an evaluation is created by the LLM
judge with a matching model_pricing entry.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712_0007"
down_revision: str | None = "20260712_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evaluation", sa.Column("judge_input_tokens", sa.Integer(), nullable=True))
    op.add_column("evaluation", sa.Column("judge_output_tokens", sa.Integer(), nullable=True))
    op.add_column("evaluation", sa.Column("judge_model", sa.String(length=120), nullable=True))
    op.add_column("evaluation", sa.Column("judge_cost_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluation", "judge_cost_usd")
    op.drop_column("evaluation", "judge_model")
    op.drop_column("evaluation", "judge_output_tokens")
    op.drop_column("evaluation", "judge_input_tokens")
