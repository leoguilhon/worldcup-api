"""add scrape runs

Revision ID: 0008_scrape_runs
Revises: 0007_status_detail
Create Date: 2026-06-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0008_scrape_runs"
down_revision: Union[str, None] = "0007_status_detail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


scrape_run_status = postgresql.ENUM("RUNNING", "SUCCESS", "FAILED", "PARSE_ERROR", name="scrape_run_status")


def upgrade() -> None:
    bind = op.get_bind()
    scrape_run_status.create(bind, checkfirst=True)
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("RUNNING", "SUCCESS", "FAILED", "PARSE_ERROR", name="scrape_run_status", create_type=False),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scrape_runs_id"), "scrape_runs", ["id"], unique=False)
    op.create_index(op.f("ix_scrape_runs_source"), "scrape_runs", ["source"], unique=False)
    op.create_index(op.f("ix_scrape_runs_status"), "scrape_runs", ["status"], unique=False)
    op.create_index(op.f("ix_scrape_runs_started_at"), "scrape_runs", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scrape_runs_started_at"), table_name="scrape_runs")
    op.drop_index(op.f("ix_scrape_runs_status"), table_name="scrape_runs")
    op.drop_index(op.f("ix_scrape_runs_source"), table_name="scrape_runs")
    op.drop_index(op.f("ix_scrape_runs_id"), table_name="scrape_runs")
    op.drop_table("scrape_runs")
    scrape_run_status.drop(op.get_bind(), checkfirst=True)
