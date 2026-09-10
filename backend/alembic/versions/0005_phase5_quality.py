"""phase5 quality

Revision ID: 0005_phase5_quality
Revises: 0004_phase4_synthesis
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_phase5_quality"
down_revision: Union[str, Sequence[str], None] = "0004_phase4_synthesis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "critic",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("synthesis_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("findings", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("project_id", "synthesis_version"),
    )
    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("required_changes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "revisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.String(), nullable=False),
        sa.Column("updated_synthesis", sa.Text(), nullable=False),
        sa.Column("changed", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("revisions")
    op.drop_table("evaluations")
    op.drop_table("critic")
