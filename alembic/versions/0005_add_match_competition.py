"""add match competition

Revision ID: 0005_add_match_competition
Revises: 0004_backfill_team_country_codes
Create Date: 2026-06-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0005_add_match_competition"
down_revision: Union[str, None] = "0004_backfill_team_country_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


competition_enum = postgresql.ENUM("WORLD_CUP", "FRIENDLY", name="match_competition")


def upgrade() -> None:
    bind = op.get_bind()
    competition_enum.create(bind, checkfirst=True)
    op.add_column(
        "matches",
        sa.Column(
            "competition",
            sa.Enum("WORLD_CUP", "FRIENDLY", name="match_competition"),
            nullable=False,
            server_default="WORLD_CUP",
        ),
    )
    op.alter_column("matches", "competition", server_default=None)
    op.create_index(op.f("ix_matches_competition"), "matches", ["competition"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_matches_competition"), table_name="matches")
    op.drop_column("matches", "competition")
    competition_enum.drop(op.get_bind(), checkfirst=True)
