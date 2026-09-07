"""phase2 research and research_sources

Revision ID: 0002_phase2_research
Revises: 0001_phase1_initial
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_phase2_research"
down_revision: Union[str, Sequence[str], None] = "0001_phase1_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("solutions", sa.Text(), nullable=False),
        sa.Column("best_practices", sa.Text(), nullable=False),
        sa.Column("open_source_potential", sa.Text(), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "research_sources",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("agent_run_id", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("license_info", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("referenced_by_synthesis", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_sources_project_run", "research_sources", ["project_id", "agent_run_id"])


def downgrade() -> None:
    op.drop_index("ix_research_sources_project_run", table_name="research_sources")
    op.drop_table("research_sources")
    op.drop_table("research")
