"""Replace fixed evaluations with rubric-driven evaluations.

Revision ID: 20260710_0002
Revises: 20260710_0001
Create Date: 2026-07-10 00:00:00.000000

This pre-release migration intentionally resets existing evaluation records.
Prompt, model response, rubric, and rubric criterion records are preserved.
Downgrade restores the previous schema shape, but deleted evaluation data is not restored.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0002"
down_revision: str | None = "20260710_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("evaluation")
    op.create_table(
        "evaluation",
        sa.Column("response_id", sa.Integer(), nullable=False),
        sa.Column("rubric_id", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("justification", sa.String(), nullable=False),
        sa.Column("evaluator", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["response_id"], ["modelresponse.id"]),
        sa.ForeignKeyConstraint(["rubric_id"], ["rubric.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_response_id", "evaluation", ["response_id"])
    op.create_index("ix_evaluation_rubric_id", "evaluation", ["rubric_id"])
    op.create_table(
        "criterionscore",
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("criterion_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["criterion_id"], ["rubriccriterion.id"]),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluation.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_id", "criterion_id"),
    )
    op.create_index(
        "ix_criterionscore_criterion_id",
        "criterionscore",
        ["criterion_id"],
    )
    op.create_index(
        "ix_criterionscore_evaluation_id",
        "criterionscore",
        ["evaluation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_criterionscore_evaluation_id", table_name="criterionscore")
    op.drop_index("ix_criterionscore_criterion_id", table_name="criterionscore")
    op.drop_table("criterionscore")
    op.drop_index("ix_evaluation_rubric_id", table_name="evaluation")
    op.drop_index("ix_evaluation_response_id", table_name="evaluation")
    op.drop_table("evaluation")
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
