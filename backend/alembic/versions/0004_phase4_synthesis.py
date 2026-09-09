"""phase4 synthesis

Revision ID: 0004_phase4_synthesis
Revises: 0003_phase3_architect_challenger
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_phase4_synthesis"
down_revision: Union[str, Sequence[str], None] = "0003_phase3_architect_challenger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "synthesis",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("project_id", "version"),
    )


def downgrade() -> None:
    op.drop_table("synthesis")
