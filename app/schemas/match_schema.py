from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.match import MatchCompetition, MatchStatus, ScrapeStatus
from app.schemas.match_event_schema import MatchEventRead
from app.schemas.team_schema import TeamRead


class MatchBase(BaseModel):
    external_id: str
    espn_event_id: str | None = None
    competition: MatchCompetition = MatchCompetition.WORLD_CUP
    source_url: str
    stadium: str | None = None
    city: str | None = None
    group_name: str | None = None
    stage: str | None = None
    match_date: datetime
    status: MatchStatus = MatchStatus.UNKNOWN
    status_detail: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_penalty_score: int | None = None
    away_penalty_score: int | None = None
    minute: int | None = None
    scrape_status: ScrapeStatus | None = None


class MatchCreate(MatchBase):
    home_team_id: int | None = None
    away_team_id: int | None = None
    winner_team_id: int | None = None


class MatchRead(MatchBase):
    id: int
    home_team: TeamRead | None = None
    away_team: TeamRead | None = None
    winner_team: TeamRead | None = None
    last_scraped_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MatchDetail(MatchRead):
    events: list[MatchEventRead] = []


class StandingRead(BaseModel):
    team: TeamRead
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
