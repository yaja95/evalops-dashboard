"""Create initial application schema.

Revision ID: 20260710_0001
Revises:
Create Date: 2026-07-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt",
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("use_case", sa.String(length=80), nullable=False),
        sa.Column("owner", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rubric",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("pass_threshold", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version"),
    )
    op.create_table(
        "modelresponse",
        sa.Column("prompt_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("response_text", sa.String(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompt.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rubriccriterion",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("min_score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rubric_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["rubric_id"], ["rubric.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rubric_id", "name"),
    )
    op.create_table(
        "evaluation",
        sa.Column("response_id", sa.Integer(), nullable=False),
        sa.Column("rubric_name", sa.String(length=120), nullable=False),
        sa.Column("instruction_following_score", sa.Integer(), nullable=False),
        sa.Column("truthfulness_score", sa.Integer(), nullable=False),
        sa.Column("completeness_score", sa.Integer(), nullable=False),
        sa.Column("conciseness_score", sa.Integer(), nullable=False),
        sa.Column("safety_score", sa.Integer(), nullable=False),
        sa.Column("writing_style_score", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("failure_category", sa.String(length=120), nullable=True),
        sa.Column("justification", sa.String(), nullable=False),
        sa.Column("evaluator", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["response_id"], ["modelresponse.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("evaluation")
    op.drop_table("rubriccriterion")
    op.drop_table("modelresponse")
    op.drop_table("rubric")
    op.drop_table("prompt")
