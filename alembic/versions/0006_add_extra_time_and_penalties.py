"""add extra time and penalties support

Revision ID: 0006_extra_penalties
Revises: 0005_add_match_competition
Create Date: 2026-06-04
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0006_extra_penalties"
down_revision: Union[str, None] = "0005_add_match_competition"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE match_status ADD VALUE IF NOT EXISTS 'EXTRA_TIME'")
    op.execute("ALTER TYPE match_status ADD VALUE IF NOT EXISTS 'PENALTIES'")
    op.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS home_penalty_score INTEGER")
    op.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS away_penalty_score INTEGER")


def downgrade() -> None:
    op.drop_column("matches", "away_penalty_score")
    op.drop_column("matches", "home_penalty_score")
