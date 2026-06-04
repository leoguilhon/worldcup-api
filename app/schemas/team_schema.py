from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TeamBase(BaseModel):
    name: str
    country_code: str | None = None
    flag_url: str | None = None
    is_placeholder: bool = False


class TeamCreate(TeamBase):
    pass


class TeamRead(TeamBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
