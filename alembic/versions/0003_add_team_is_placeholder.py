"""add team placeholder flag

Revision ID: 0003_add_team_is_placeholder
Revises: 0002_add_espn_event_id
Create Date: 2026-06-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_add_team_is_placeholder"
down_revision: Union[str, None] = "0002_add_espn_event_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("is_placeholder", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(op.f("ix_teams_is_placeholder"), "teams", ["is_placeholder"], unique=False)
    op.execute(
        """
        UPDATE teams
        SET is_placeholder = true
        WHERE lower(name) LIKE 'winner group %'
           OR lower(name) LIKE 'runner-up group %'
           OR lower(name) LIKE '3rd group %'
           OR lower(name) LIKE 'winner match %'
           OR lower(name) LIKE 'loser match %'
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_teams_is_placeholder"), table_name="teams")
    op.drop_column("teams", "is_placeholder")
