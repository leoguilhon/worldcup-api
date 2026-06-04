from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.match import Match
from app.models.scrape_run import ScrapeRun, ScrapeRunStatus
from app.models.worker_heartbeat import WorkerHeartbeat
from app.schemas.scraping_schema import ScrapingStatusRead
from app.services.scraper_service import ACTIVE_MATCH_STATUSES


STALE_ACTIVE_MATCH_SECONDS = 90
WORKER_STALE_SECONDS = 120


def get_scraping_status(db: Session) -> ScrapingStatusRead:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=STALE_ACTIVE_MATCH_SECONDS)

    active_stmt = (
        select(Match)
        .where(Match.status.in_(ACTIVE_MATCH_STATUSES))
        .options(joinedload(Match.home_team), joinedload(Match.away_team), joinedload(Match.winner_team), selectinload(Match.events))
        .order_by(Match.match_date.asc())
    )
    active_matches = list(db.scalars(active_stmt).unique())
    stale_matches = [
        match for match in active_matches if not match.last_scraped_at or _as_utc(match.last_scraped_at) < stale_before
    ]

    recent_runs = list(
        db.scalars(select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(10))
    )
    last_run = recent_runs[0] if recent_runs else None
    last_success_at = db.scalar(
        select(ScrapeRun.finished_at)
        .where(ScrapeRun.status == ScrapeRunStatus.SUCCESS)
        .order_by(desc(ScrapeRun.finished_at))
        .limit(1)
    )
    heartbeat = db.get(WorkerHeartbeat, "live_score_worker")
    worker_status = "unknown"
    if heartbeat:
        worker_status = "ok" if _as_utc(heartbeat.last_seen_at) >= now - timedelta(seconds=WORKER_STALE_SECONDS) else "stale"

    status = "ok"
    if worker_status != "ok" or stale_matches:
        status = "degraded"
    if last_run and last_run.status in {ScrapeRunStatus.FAILED, ScrapeRunStatus.PARSE_ERROR}:
        status = "degraded"
    if not last_run:
        status = "unknown"

    return ScrapingStatusRead(
        status=status,
        now=now,
        worker_status=worker_status,
        worker_last_seen_at=heartbeat.last_seen_at if heartbeat else None,
        worker_stale_threshold_seconds=WORKER_STALE_SECONDS,
        active_matches_count=len(active_matches),
        stale_active_matches_count=len(stale_matches),
        stale_threshold_seconds=STALE_ACTIVE_MATCH_SECONDS,
        last_success_at=last_success_at,
        last_run=last_run,
        recent_runs=recent_runs,
        stale_active_matches=stale_matches,
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
