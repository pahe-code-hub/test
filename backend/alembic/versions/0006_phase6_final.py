"""phase6 final

Revision ID: 0006_phase6_final
Revises: 0005_phase5_quality
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_phase6_final"
down_revision: Union[str, Sequence[str], None] = "0005_phase5_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("presentation", sa.Text(), nullable=False),
        sa.Column("open_decisions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("final")
