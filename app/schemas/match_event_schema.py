from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.team_schema import TeamRead


class MatchEventBase(BaseModel):
    team_id: int | None = None
    player_name: str | None = None
    event_type: str
    minute: int | None = None
    extra_minute: int | None = None


class MatchEventCreate(MatchEventBase):
    match_id: int


class MatchEventRead(MatchEventBase):
    id: int
    match_id: int
    created_at: datetime
    team: TeamRead | None = None

    model_config = ConfigDict(from_attributes=True)
