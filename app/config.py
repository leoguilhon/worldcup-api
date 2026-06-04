from functools import lru_cache
from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WorldCup API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://worldcup:worldcup@localhost:5432/worldcup"
    cors_allowed_origins: str = ""

    scraper_user_agent: str = "WorldCupBot/1.0 (+https://example.com/bot)"
    scraper_timeout_seconds: int = 10
    scraper_min_request_interval_seconds: int = 5
    schedule_scrape_interval_hours: int = 6
    live_scrape_interval_seconds: int = 60
    source_provider: str = "wikipedia_2026"
    source_base_url: str = "https://example.com/world-cup"
    source_schedule_url: str = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup"
    live_score_provider: str = "espn_worldcup"
    espn_scoreboard_url: str = "https://www.espn.com/soccer/scoreboard/_/league/fifa.world"
    espn_friendly_scoreboard_url: str = "https://www.espn.com/soccer/scoreboard/_/league/fifa.friendly"
    espn_test_scoreboard_url: str = "https://www.espn.com/soccer/scoreboard/_/league/fifa.friendly/date/20260606"
    espn_test_event_id: str = "401861998"
    friendly_tracking_enabled: bool = True
    friendly_tracking_start_date: date = date(2026, 6, 1)
    friendly_tracking_end_date: date = date(2026, 6, 10)
    friendly_discovery_interval_hours: int = 12
    live_score_window_before_minutes: int = 180
    live_score_window_after_minutes: int = 240

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
