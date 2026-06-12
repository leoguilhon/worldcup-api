import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.match import Match, MatchCompetition, MatchStatus, ScrapeStatus
from app.models.match_event import MatchEvent
from app.models.scrape_run import ScrapeRun, ScrapeRunStatus
from app.models.team import Team
from app.utils.team_codes import country_code_for_team
from app.utils.http_client import ScraperHttpClient


logger = logging.getLogger(__name__)
ACTIVE_MATCH_STATUSES = (MatchStatus.LIVE, MatchStatus.HALF_TIME, MatchStatus.EXTRA_TIME, MatchStatus.PENALTIES)
EXPIRED_ACTIVE_STATUS_DETAIL = "Stale live status expired"


class ParserError(ValueError):
    pass


@dataclass
class ScrapedMatch:
    external_id: str
    source_url: str
    home_team: str
    away_team: str
    match_date: datetime
    espn_event_id: str | None = None
    home_flag_url: str | None = None
    away_flag_url: str | None = None
    stadium: str | None = None
    city: str | None = None
    group_name: str | None = None
    stage: str | None = None
    status: MatchStatus = MatchStatus.UNKNOWN
    status_detail: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_penalty_score: int | None = None
    away_penalty_score: int | None = None
    minute: int | None = None
    winner_team: str | None = None
    events: list[dict] | None = None
    competition: MatchCompetition = MatchCompetition.WORLD_CUP


def parse_match_html(html: str) -> dict:
    """Parse one match page using generic data attributes that are easy to remap later."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("[data-match]")
    if not root:
        raise ParserError("Missing [data-match] root element")

    status_text = _text(root, "[data-status]", default="UNKNOWN")
    score_text = _text(root, "[data-score]", default="-")
    minute_text = _text(root, "[data-minute]", default="")

    home_score, away_score = _parse_score(score_text)
    events = []
    for event_node in root.select("[data-event]"):
        minute, extra_minute = _parse_minute(event_node.get("data-minute") or "")
        events.append(
            {
                "team_name": event_node.get("data-team") or None,
                "player_name": _text(event_node, "[data-player]", default=None),
                "event_type": event_node.get("data-type") or "UNKNOWN",
                "minute": minute,
                "extra_minute": extra_minute,
            }
        )

    minute, _ = _parse_minute(minute_text)
    return {
        "status": _normalize_match_status(status_text).value,
        "home_score": home_score,
        "away_score": away_score,
        "minute": minute,
        "events": events,
    }


class ScraperService:
    def __init__(self, http_client: ScraperHttpClient | None = None) -> None:
        self.settings = get_settings()
        self.http_client = http_client or ScraperHttpClient()

    def scrape_schedule(self, db: Session) -> None:
        run = start_scrape_run(db, "schedule")
        if self.settings.source_provider == "wikipedia_2026":
            from app.services.providers.wikipedia_2026 import parse_wikipedia_2026_schedule

            url = self.settings.source_schedule_url
            parser = lambda html: parse_wikipedia_2026_schedule(html, url)
        else:
            url = urljoin(self.settings.source_base_url.rstrip("/") + "/", "schedule")
            parser = lambda html: parse_schedule_html(html, self.settings.source_base_url)

        logger.info("Scraping schedule from %s", url)
        try:
            html = self.http_client.get(url)
            matches = parser(html)
            for item in matches:
                upsert_match(db, item, ScrapeStatus.SUCCESS)
            finish_scrape_run(run, ScrapeRunStatus.SUCCESS, parsed_count=len(matches), applied_count=len(matches))
            db.commit()
            logger.info("Schedule scrape finished: %d matches", len(matches))
        except ParserError as exc:
            db.rollback()
            fail_scrape_run(db, run, ScrapeRunStatus.PARSE_ERROR, exc)
            logger.exception("Schedule parse error")
        except Exception as exc:
            db.rollback()
            fail_scrape_run(db, run, ScrapeRunStatus.FAILED, exc)
            logger.exception("Schedule scrape failed")

    def scrape_live_matches(self, db: Session) -> None:
        expired = expire_stale_active_matches(db, self.settings.live_score_window_after_minutes)
        if expired:
            db.commit()
            logger.info("Expired %d stale active match(es)", expired)

        if self.settings.live_score_provider == "espn_worldcup":
            self.scrape_espn_scoreboard(db)
            return

        matches = get_candidate_live_matches(db, self.settings.live_score_window_before_minutes, self.settings.live_score_window_after_minutes)
        logger.info("Scraping %d live match pages", len(matches))

        for match in matches:
            self._scrape_match_page(db, match)

    def scrape_espn_scoreboard(self, db: Session) -> None:
        from app.services.providers.espn_worldcup import build_scoreboard_url, parse_espn_scoreboard_html

        targets = get_espn_scoreboard_targets(
            db,
            before_minutes=self.settings.live_score_window_before_minutes,
            after_minutes=self.settings.live_score_window_after_minutes,
            worldcup_base_url=self.settings.espn_scoreboard_url,
            friendly_base_url=self.settings.espn_friendly_scoreboard_url,
            include_friendlies=self.settings.friendly_tracking_enabled,
        )

        logger.info(
            "Scraping ESPN scoreboard for %d target(s)",
            len(targets),
        )
        for match_day, base_url in targets:
            url = build_scoreboard_url(base_url, match_day)
            run = start_scrape_run(db, f"espn_scoreboard:{url}")
            try:
                html = self.http_client.get(url)
                updates = parse_espn_scoreboard_html(html)
                applied = 0
                for update in updates:
                    match = find_match_for_espn_update(db, update)
                    if not match:
                        continue
                    apply_espn_update(db, match, update)
                    applied += 1
                finish_scrape_run(run, ScrapeRunStatus.SUCCESS, parsed_count=len(updates), applied_count=applied)
                db.commit()
                logger.info(
                    "ESPN scoreboard %s parsed=%d applied=%d url=%s",
                    match_day.isoformat(),
                    len(updates),
                    applied,
                    url,
                )
            except ParserError as exc:
                db.rollback()
                fail_scrape_run(db, run, ScrapeRunStatus.PARSE_ERROR, exc)
                mark_candidates_scrape_status(db, match_day, ScrapeStatus.PARSE_ERROR)
                logger.exception("ESPN scoreboard parse error for %s url=%s", match_day.isoformat(), url)
            except Exception as exc:
                db.rollback()
                fail_scrape_run(db, run, ScrapeRunStatus.FAILED, exc)
                mark_candidates_scrape_status(db, match_day, ScrapeStatus.FAILED)
                logger.exception("ESPN scoreboard scrape failed for %s url=%s", match_day.isoformat(), url)

    def discover_espn_friendlies(self, db: Session) -> None:
        if not self.settings.friendly_tracking_enabled:
            logger.info("Friendly tracking is disabled")
            return

        from app.services.providers.espn_worldcup import build_scoreboard_url, parse_espn_scoreboard_html

        tracked_teams = get_tracked_team_names(db)
        if not tracked_teams:
            logger.info("No tracked teams found for friendly discovery")
            return

        run = start_scrape_run(db, "espn_friendlies_discovery")
        discovered = 0
        parsed_total = 0
        for match_day in _date_range(self.settings.friendly_tracking_start_date, self.settings.friendly_tracking_end_date):
            url = build_scoreboard_url(self.settings.espn_friendly_scoreboard_url, match_day)
            try:
                html = self.http_client.get(url)
                updates = parse_espn_scoreboard_html(html)
                parsed_total += len(updates)
                applied = 0
                for update in updates:
                    if not is_friendly_for_tracked_team(update, tracked_teams):
                        continue
                    upsert_espn_friendly(db, update)
                    applied += 1
                db.commit()
                discovered += applied
                logger.info("ESPN friendlies %s parsed=%d tracked=%d", match_day.isoformat(), len(updates), applied)
            except ParserError as exc:
                db.rollback()
                fail_scrape_run(db, run, ScrapeRunStatus.PARSE_ERROR, exc)
                logger.exception("ESPN friendly parse error for %s", match_day.isoformat())
                return
            except Exception as exc:
                db.rollback()
                fail_scrape_run(db, run, ScrapeRunStatus.FAILED, exc)
                logger.exception("ESPN friendly scrape failed for %s", match_day.isoformat())
                return

        finish_scrape_run(run, ScrapeRunStatus.SUCCESS, parsed_count=parsed_total, applied_count=discovered)
        db.commit()
        logger.info("Friendly discovery finished: %d tracked match(es)", discovered)

    def _scrape_match_page(self, db: Session, match: Match) -> None:
        try:
            html = self.http_client.get(match.source_url)
            parsed = parse_match_html(html)
            apply_live_payload(db, match, parsed, ScrapeStatus.SUCCESS)
            db.commit()
            logger.info("Updated live match %s", match.external_id)
        except ParserError:
            db.rollback()
            mark_match_scrape_status(db, match.id, ScrapeStatus.PARSE_ERROR)
            logger.exception("Parse error for match %s", match.external_id)
        except Exception:
            db.rollback()
            mark_match_scrape_status(db, match.id, ScrapeStatus.FAILED)
            logger.exception("Scrape failed for match %s", match.external_id)


def parse_schedule_html(html: str, base_url: str) -> list[ScrapedMatch]:
    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select("[data-match-card]")
    if not nodes:
        raise ParserError("Missing match cards in schedule HTML")

    matches = []
    for node in nodes:
        external_id = node.get("data-external-id")
        if not external_id:
            raise ParserError("Match card without data-external-id")
        match_url = node.get("data-source-url") or f"/matches/{external_id}"
        matches.append(
            ScrapedMatch(
                external_id=external_id,
                source_url=urljoin(base_url, match_url),
                home_team=_text(node, "[data-home-team]", required=True),
                away_team=_text(node, "[data-away-team]", required=True),
                match_date=_parse_datetime(_text(node, "[data-match-date]", required=True)),
                stadium=_text(node, "[data-stadium]", default=None),
                city=_text(node, "[data-city]", default=None),
                group_name=_text(node, "[data-group]", default=None),
                stage=_text(node, "[data-stage]", default=None),
                status=_normalize_match_status(_text(node, "[data-status]", default="UNKNOWN")),
                home_score=None,
                away_score=None,
                minute=None,
                events=[],
            )
        )
    return matches


def start_scrape_run(db: Session, source: str) -> ScrapeRun:
    run = ScrapeRun(
        source=source,
        status=ScrapeRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        parsed_count=0,
        applied_count=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_scrape_run(
    run: ScrapeRun,
    status: ScrapeRunStatus,
    *,
    parsed_count: int,
    applied_count: int,
) -> None:
    run.status = status
    run.finished_at = datetime.now(timezone.utc)
    run.parsed_count = parsed_count
    run.applied_count = applied_count
    run.error_message = None


def fail_scrape_run(db: Session, run: ScrapeRun, status: ScrapeRunStatus, exc: Exception) -> None:
    persisted = db.get(ScrapeRun, run.id)
    if not persisted:
        persisted = run
        db.add(persisted)
    persisted.status = status
    persisted.finished_at = datetime.now(timezone.utc)
    persisted.error_message = str(exc)[:2000]
    db.commit()


def upsert_match(db: Session, item: ScrapedMatch, scrape_status: ScrapeStatus) -> Match:
    home_team = get_or_create_team(db, item.home_team, item.home_flag_url)
    away_team = get_or_create_team(db, item.away_team, item.away_flag_url)
    match = db.scalar(select(Match).where(Match.external_id == item.external_id))
    if not match:
        match = Match(external_id=item.external_id, source_url=item.source_url, match_date=item.match_date)
        db.add(match)

    match.espn_event_id = item.espn_event_id or match.espn_event_id
    match.competition = item.competition
    match.source_url = item.source_url
    match.home_team = home_team
    match.away_team = away_team
    match.stadium = item.stadium
    match.city = item.city
    match.group_name = item.group_name
    match.stage = item.stage
    match.match_date = item.match_date
    preserve_live_fields = item.espn_event_id is None and match.espn_event_id is not None
    if not preserve_live_fields:
        match.status = item.status
        match.status_detail = item.status_detail
        match.home_score = item.home_score
        match.away_score = item.away_score
        match.home_penalty_score = item.home_penalty_score
        match.away_penalty_score = item.away_penalty_score
        match.minute = item.minute
        match.winner_team = get_or_create_team(db, item.winner_team) if item.winner_team else None
        match.last_scraped_at = datetime.now(timezone.utc)
        match.scrape_status = scrape_status
    return match


def apply_live_payload(db: Session, match: Match, payload: dict, scrape_status: ScrapeStatus) -> None:
    match.status = MatchStatus(payload.get("status", MatchStatus.UNKNOWN.value))
    match.status_detail = payload.get("status_detail")
    match.home_score = payload.get("home_score")
    match.away_score = payload.get("away_score")
    match.home_penalty_score = payload.get("home_penalty_score")
    match.away_penalty_score = payload.get("away_penalty_score")
    match.minute = payload.get("minute")
    match.last_scraped_at = datetime.now(timezone.utc)
    match.scrape_status = scrape_status

    match.events.clear()
    for event in payload.get("events", []):
        team = get_or_create_team(db, event["team_name"]) if event.get("team_name") else None
        match.events.append(
            MatchEvent(
                team=team,
                player_name=event.get("player_name"),
                event_type=event.get("event_type") or "UNKNOWN",
                minute=event.get("minute"),
                extra_minute=event.get("extra_minute"),
            )
        )


def apply_espn_update(db: Session, match: Match, update) -> None:
    home_team = get_or_create_team(db, _canonical_team_name(update.home_team), update.home_flag_url)
    away_team = get_or_create_team(db, _canonical_team_name(update.away_team), update.away_flag_url)
    match.espn_event_id = update.espn_event_id
    match.source_url = update.source_url
    match.home_team = home_team
    match.away_team = away_team
    match.match_date = update.match_date
    match.status = update.status
    match.status_detail = update.status_detail
    match.home_score = update.home_score
    match.away_score = update.away_score
    match.home_penalty_score = update.home_penalty_score
    match.away_penalty_score = update.away_penalty_score
    match.minute = update.minute
    match.stadium = update.stadium or match.stadium
    match.city = update.city or match.city
    match.winner_team = get_or_create_team(db, _canonical_team_name(update.winner_team)) if update.winner_team else None
    match.last_scraped_at = datetime.now(timezone.utc)
    match.scrape_status = ScrapeStatus.SUCCESS
    replace_match_events(db, match, update.events or [])


def replace_match_events(db: Session, match: Match, events: list[dict]) -> None:
    match.events.clear()
    for event in events:
        team = get_or_create_team(db, event["team_name"]) if event.get("team_name") else None
        match.events.append(
            MatchEvent(
                team=team,
                player_name=event.get("player_name"),
                event_type=event.get("event_type") or "UNKNOWN",
                minute=event.get("minute"),
                extra_minute=event.get("extra_minute"),
            )
        )


def upsert_espn_friendly(db: Session, update) -> Match:
    item = ScrapedMatch(
        external_id=f"espn-friendly-{update.espn_event_id}",
        espn_event_id=update.espn_event_id,
        source_url=update.source_url,
        home_team=update.home_team,
        away_team=update.away_team,
        home_flag_url=update.home_flag_url,
        away_flag_url=update.away_flag_url,
        match_date=update.match_date,
        stadium=update.stadium,
        city=update.city,
        group_name=None,
        stage="Friendly",
        status=update.status,
        status_detail=update.status_detail,
        home_score=update.home_score,
        away_score=update.away_score,
        home_penalty_score=update.home_penalty_score,
        away_penalty_score=update.away_penalty_score,
        minute=update.minute,
        winner_team=update.winner_team,
        events=update.events or [],
        competition=MatchCompetition.FRIENDLY,
    )
    return upsert_match(db, item, ScrapeStatus.SUCCESS)


def find_match_for_espn_update(db: Session, update) -> Match | None:
    match = db.scalar(select(Match).where(Match.espn_event_id == update.espn_event_id))
    if match:
        return match

    start = update.match_date - timedelta(hours=18)
    end = update.match_date + timedelta(hours=18)
    candidates = db.scalars(select(Match).where(and_(Match.match_date >= start, Match.match_date <= end))).all()
    update_home = _normalize_team_name(update.home_team)
    update_away = _normalize_team_name(update.away_team)
    for candidate in candidates:
        if not candidate.home_team or not candidate.away_team:
            continue
        candidate_home = _normalize_team_name(candidate.home_team.name)
        candidate_away = _normalize_team_name(candidate.away_team.name)
        if candidate_home == update_home and candidate_away == update_away:
            return candidate

    same_time_candidates = [
        candidate
        for candidate in candidates
        if candidate.espn_event_id is None and abs((candidate.match_date - update.match_date).total_seconds()) <= 600
    ]
    if len(same_time_candidates) == 1:
        return same_time_candidates[0]
    return None


def get_candidate_live_matches(
    db: Session,
    before_minutes: int,
    after_minutes: int,
    competition: MatchCompetition | None = None,
    now: datetime | None = None,
) -> list[Match]:
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(minutes=before_minutes)
    end = now + timedelta(minutes=after_minutes)
    stmt = (
        select(Match)
        .where(
            or_(
                and_(Match.status.in_(ACTIVE_MATCH_STATUSES), Match.match_date >= start, Match.match_date <= end),
                and_(Match.status == MatchStatus.SCHEDULED, Match.match_date >= start, Match.match_date <= end),
            )
        )
        .order_by(Match.match_date.asc())
    )
    if competition:
        stmt = stmt.where(Match.competition == competition)
    return list(db.scalars(stmt))


def expire_stale_active_matches(db: Session, after_minutes: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=after_minutes)
    matches = list(
        db.scalars(
            select(Match).where(
                Match.status.in_(ACTIVE_MATCH_STATUSES),
                Match.match_date < cutoff,
            )
        )
    )
    now = datetime.now(timezone.utc)
    for match in matches:
        match.status = MatchStatus.UNKNOWN
        match.status_detail = EXPIRED_ACTIVE_STATUS_DETAIL
        match.minute = None
        match.last_scraped_at = now
    return len(matches)


def get_candidate_scoreboard_dates(
    db: Session,
    before_minutes: int,
    after_minutes: int,
    competition: MatchCompetition | None = None,
    now: datetime | None = None,
) -> set:
    matches = get_candidate_live_matches(
        db,
        before_minutes,
        after_minutes,
        competition=competition,
        now=now,
    )
    dates = set()
    for match in matches:
        match_date = match.match_date.astimezone(timezone.utc)
        dates.add(match_date.date())
        dates.add((match_date - timedelta(days=1)).date())
        dates.add((match_date + timedelta(days=1)).date())
    return dates


def has_active_matches(db: Session) -> bool:
    stmt = select(Match.id).where(Match.status.in_(ACTIVE_MATCH_STATUSES)).limit(1)
    return db.scalar(stmt) is not None


def get_espn_scoreboard_targets(
    db: Session,
    *,
    before_minutes: int,
    after_minutes: int,
    worldcup_base_url: str,
    friendly_base_url: str,
    include_friendlies: bool,
) -> list[tuple[date, str]]:
    targets: list[tuple[date, str]] = []

    worldcup_dates = get_candidate_scoreboard_dates(
        db, before_minutes, after_minutes, MatchCompetition.WORLD_CUP
    )
    targets.extend((match_day, worldcup_base_url) for match_day in sorted(worldcup_dates))

    if include_friendlies:
        friendly_dates = get_candidate_scoreboard_dates(
            db, before_minutes, after_minutes, MatchCompetition.FRIENDLY
        )
        targets.extend((match_day, friendly_base_url) for match_day in sorted(friendly_dates))

    if targets:
        return targets

    next_match = get_next_scheduled_match(db)
    if not next_match:
        return [(datetime.now(timezone.utc).date(), worldcup_base_url)]

    base_url = friendly_base_url if next_match.competition == MatchCompetition.FRIENDLY else worldcup_base_url
    return [(next_match.match_date.astimezone(timezone.utc).date(), base_url)]


def get_next_scheduled_match(db: Session) -> Match | None:
    now = datetime.now(timezone.utc)
    stmt = select(Match).where(Match.match_date >= now).order_by(Match.match_date.asc()).limit(1)
    return db.scalar(stmt)


def get_tracked_team_names(db: Session) -> set[str]:
    stmt = select(Team.name).where(Team.is_placeholder.is_(False))
    return {_normalize_team_name(name) for name in db.scalars(stmt) if name}


def is_friendly_for_tracked_team(update, tracked_teams: set[str]) -> bool:
    return _normalize_team_name(update.home_team) in tracked_teams or _normalize_team_name(update.away_team) in tracked_teams


def _date_range(start: date, end: date):
    if end < start:
        return
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def mark_candidates_scrape_status(db: Session, match_day, status: ScrapeStatus) -> None:
    start = datetime.combine(match_day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    for match in db.scalars(select(Match).where(and_(Match.match_date >= start, Match.match_date < end))):
        match.scrape_status = status
        match.last_scraped_at = datetime.now(timezone.utc)
    db.commit()


def mark_match_scrape_status(db: Session, match_id: int, status: ScrapeStatus) -> None:
    match = db.get(Match, match_id)
    if match:
        match.scrape_status = status
        match.last_scraped_at = datetime.now(timezone.utc)
        db.commit()


def get_or_create_team(db: Session, name: str, flag_url: str | None = None) -> Team:
    name = _canonical_team_name(name)
    is_placeholder = _is_placeholder_team_name(name)
    team = db.scalar(select(Team).where(Team.name == name))
    if team:
        team.is_placeholder = is_placeholder
        if not is_placeholder and not team.country_code:
            team.country_code = country_code_for_team(name)
        if flag_url and not team.flag_url:
            team.flag_url = flag_url
        return team
    team = Team(
        name=name,
        country_code=None if is_placeholder else country_code_for_team(name),
        flag_url=flag_url,
        is_placeholder=is_placeholder,
    )
    db.add(team)
    db.flush()
    return team


def _canonical_team_name(name: str) -> str:
    aliases = {
        "Czechia": "Czech Republic",
        "Türkiye": "Turkey",
        "Turkiye": "Turkey",
        "USA": "United States",
    }
    return aliases.get(name, name)


def _normalize_team_name(name: str) -> str:
    value = _canonical_team_name(name)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re_sub_non_word(value.lower())


def _is_placeholder_team_name(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized.startswith(
        (
            "winner group ",
            "runner-up group ",
            "3rd group ",
            "winner match ",
            "loser match ",
        )
    )


def re_sub_non_word(value: str) -> str:
    return "".join(char for char in value if char.isalnum())


def _text(node, selector: str, *, default: str | None = "", required: bool = False) -> str | None:
    found = node.select_one(selector)
    if not found:
        if required:
            raise ParserError(f"Missing selector: {selector}")
        return default
    value = found.get_text(strip=True)
    if required and not value:
        raise ParserError(f"Empty selector: {selector}")
    return value or default


def _parse_score(value: str) -> tuple[int | None, int | None]:
    if not value or "-" not in value:
        return None, None
    left, right = value.split("-", 1)
    try:
        return int(left.strip()), int(right.strip())
    except ValueError as exc:
        raise ParserError(f"Invalid score: {value}") from exc


def _parse_minute(value: str) -> tuple[int | None, int | None]:
    cleaned = value.replace("'", "").strip()
    if not cleaned:
        return None, None
    if "+" in cleaned:
        base, extra = cleaned.split("+", 1)
        return int(base), int(extra)
    return int(cleaned), None


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ParserError(f"Invalid date: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_match_status(value: str | None) -> MatchStatus:
    normalized = (value or "UNKNOWN").strip().upper().replace(" ", "_").replace("-", "_")
    return MatchStatus.__members__.get(normalized, MatchStatus.UNKNOWN)
