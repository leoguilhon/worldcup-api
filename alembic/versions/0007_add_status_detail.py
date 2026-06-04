"""add match status detail

Revision ID: 0007_status_detail
Revises: 0006_extra_penalties
Create Date: 2026-06-04
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0007_status_detail"
down_revision: Union[str, None] = "0006_extra_penalties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS status_detail VARCHAR(120)")


def downgrade() -> None:
    op.drop_column("matches", "status_detail")
