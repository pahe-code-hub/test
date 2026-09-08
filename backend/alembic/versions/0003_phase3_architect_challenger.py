"""phase3 architect and challenger

Revision ID: 0003_phase3_architect_challenger
Revises: 0002_phase2_research
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_phase3_architect_challenger"
down_revision: Union[str, Sequence[str], None] = "0002_phase2_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("architect", "challenger"):
        op.create_table(
            table_name,
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("output", sa.Text(), nullable=True),
            sa.Column("run_status", sa.String(), nullable=False, server_default="PENDING"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("project_id"),
        )


def downgrade() -> None:
    op.drop_table("challenger")
    op.drop_table("architect")
