"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

match_status = postgresql.ENUM(
    "SCHEDULED",
    "LIVE",
    "HALF_TIME",
    "FINISHED",
    "POSTPONED",
    "CANCELLED",
    "UNKNOWN",
    name="match_status",
    create_type=False,
)
scrape_status = postgresql.ENUM(
    "SUCCESS",
    "FAILED",
    "PARSE_ERROR",
    name="scrape_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE match_status AS ENUM (
                'SCHEDULED',
                'LIVE',
                'HALF_TIME',
                'FINISHED',
                'POSTPONED',
                'CANCELLED',
                'UNKNOWN'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE scrape_status AS ENUM ('SUCCESS', 'FAILED', 'PARSE_ERROR');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=True),
        sa.Column("flag_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_teams_id"), "teams", ["id"], unique=False)
    op.create_index(op.f("ix_teams_name"), "teams", ["name"], unique=False)
    op.create_index(op.f("ix_teams_country_code"), "teams", ["country_code"], unique=False)

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=True),
        sa.Column("away_team_id", sa.Integer(), nullable=True),
        sa.Column("stadium", sa.String(length=160), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("group_name", sa.String(length=80), nullable=True),
        sa.Column("stage", sa.String(length=80), nullable=True),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", match_status, nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("minute", sa.Integer(), nullable=True),
        sa.Column("winner_team_id", sa.Integer(), nullable=True),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scrape_status", scrape_status, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["away_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["home_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["winner_team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_matches_external_id"),
    )
    op.create_index(op.f("ix_matches_id"), "matches", ["id"], unique=False)
    op.create_index(op.f("ix_matches_external_id"), "matches", ["external_id"], unique=False)
    op.create_index(op.f("ix_matches_group_name"), "matches", ["group_name"], unique=False)
    op.create_index(op.f("ix_matches_stage"), "matches", ["stage"], unique=False)
    op.create_index(op.f("ix_matches_match_date"), "matches", ["match_date"], unique=False)
    op.create_index(op.f("ix_matches_status"), "matches", ["status"], unique=False)
    op.create_index(op.f("ix_matches_scrape_status"), "matches", ["scrape_status"], unique=False)

    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("player_name", sa.String(length=160), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=True),
        sa.Column("extra_minute", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_match_events_id"), "match_events", ["id"], unique=False)
    op.create_index(op.f("ix_match_events_match_id"), "match_events", ["match_id"], unique=False)
    op.create_index(op.f("ix_match_events_event_type"), "match_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_match_events_event_type"), table_name="match_events")
    op.drop_index(op.f("ix_match_events_match_id"), table_name="match_events")
    op.drop_index(op.f("ix_match_events_id"), table_name="match_events")
    op.drop_table("match_events")
    op.drop_index(op.f("ix_matches_scrape_status"), table_name="matches")
    op.drop_index(op.f("ix_matches_status"), table_name="matches")
    op.drop_index(op.f("ix_matches_match_date"), table_name="matches")
    op.drop_index(op.f("ix_matches_stage"), table_name="matches")
    op.drop_index(op.f("ix_matches_group_name"), table_name="matches")
    op.drop_index(op.f("ix_matches_external_id"), table_name="matches")
    op.drop_index(op.f("ix_matches_id"), table_name="matches")
    op.drop_table("matches")
    op.drop_index(op.f("ix_teams_country_code"), table_name="teams")
    op.drop_index(op.f("ix_teams_name"), table_name="teams")
    op.drop_index(op.f("ix_teams_id"), table_name="teams")
    op.drop_table("teams")
    scrape_status.drop(op.get_bind(), checkfirst=True)
    match_status.drop(op.get_bind(), checkfirst=True)
