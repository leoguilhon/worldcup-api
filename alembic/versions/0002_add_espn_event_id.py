"""add espn event id

Revision ID: 0002_add_espn_event_id
Revises: 0001_initial
Create Date: 2026-06-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_espn_event_id"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("espn_event_id", sa.String(length=40), nullable=True))
    op.create_index(op.f("ix_matches_espn_event_id"), "matches", ["espn_event_id"], unique=False)
    op.create_unique_constraint("uq_matches_espn_event_id", "matches", ["espn_event_id"])


def downgrade() -> None:
    op.drop_constraint("uq_matches_espn_event_id", "matches", type_="unique")
    op.drop_index(op.f("ix_matches_espn_event_id"), table_name="matches")
    op.drop_column("matches", "espn_event_id")
