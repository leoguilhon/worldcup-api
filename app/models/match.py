import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MatchStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    HALF_TIME = "HALF_TIME"
    EXTRA_TIME = "EXTRA_TIME"
    PENALTIES = "PENALTIES"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class ScrapeStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARSE_ERROR = "PARSE_ERROR"


class MatchCompetition(str, enum.Enum):
    WORLD_CUP = "WORLD_CUP"
    FRIENDLY = "FRIENDLY"


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("external_id", name="uq_matches_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    espn_event_id: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True, index=True)
    competition: Mapped[MatchCompetition] = mapped_column(
        Enum(MatchCompetition, name="match_competition"), default=MatchCompetition.WORLD_CUP, index=True
    )
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    home_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    away_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    stadium: Mapped[str | None] = mapped_column(String(160), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    stage: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    match_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, name="match_status"), default=MatchStatus.UNKNOWN, index=True
    )
    status_detail: Mapped[str | None] = mapped_column(String(120), nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_penalty_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_penalty_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scrape_status: Mapped[ScrapeStatus | None] = mapped_column(
        Enum(ScrapeStatus, name="scrape_status"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_matches")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_matches")
    winner_team = relationship("Team", foreign_keys=[winner_team_id], back_populates="won_matches")
    events = relationship("MatchEvent", back_populates="match", cascade="all, delete-orphan")
