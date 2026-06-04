from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.scrape_run import ScrapeRunStatus
from app.schemas.match_schema import MatchRead


class ScrapeRunRead(BaseModel):
    id: int
    source: str
    status: ScrapeRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    parsed_count: int
    applied_count: int
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ScrapingStatusRead(BaseModel):
    status: str
    now: datetime
    worker_status: str
    worker_last_seen_at: datetime | None = None
    worker_stale_threshold_seconds: int
    active_matches_count: int
    stale_active_matches_count: int
    stale_threshold_seconds: int
    last_success_at: datetime | None = None
    last_run: ScrapeRunRead | None = None
    recent_runs: list[ScrapeRunRead]
    stale_active_matches: list[MatchRead]
