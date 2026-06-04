import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.models.match import MatchStatus
from app.services.scraper_service import ParserError


ESPN_BASE_URL = "https://www.espn.com"


@dataclass
class EspnLiveMatch:
    espn_event_id: str
    source_url: str
    home_team: str
    away_team: str
    match_date: datetime
    status: MatchStatus
    status_detail: str | None
    home_score: int | None
    away_score: int | None
    minute: int | None
    winner_team: str | None = None
    home_penalty_score: int | None = None
    away_penalty_score: int | None = None
    stadium: str | None = None
    city: str | None = None
    home_flag_url: str | None = None
    away_flag_url: str | None = None
    events: list[dict] | None = None


def build_scoreboard_url(base_url: str, match_date: date | None = None) -> str:
    if not match_date:
        return base_url
    return f"{base_url.rstrip('/')}/date/{match_date:%Y%m%d}"


def parse_espn_scoreboard_html(html: str) -> list[EspnLiveMatch]:
    state = _extract_state(html)
    leagues = _find_key(state, "gmsByLeague")
    if not isinstance(leagues, list):
        raise ParserError("ESPN scoreboard state does not contain gmsByLeague")

    matches: list[EspnLiveMatch] = []
    for league in leagues:
        for event in league.get("evts", []):
            parsed = _parse_event(event)
            if parsed:
                matches.append(parsed)

    return matches


def _extract_state(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        marker = "window['__espnfitt__']="
        if marker not in text:
            continue
        start = text.index(marker) + len(marker)
        json_text = _read_json_object(text, start)
        try:
            return json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ParserError("Invalid ESPN embedded JSON") from exc
    raise ParserError("Missing ESPN embedded state")


def _read_json_object(text: str, start: int) -> str:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ParserError("Could not read ESPN state object")


def _find_key(value, key: str):
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def _parse_event(event: dict) -> EspnLiveMatch | None:
    competitors = event.get("competitors") or event.get("teams") or []
    home = _competitor_by_home_flag(competitors, True)
    away = _competitor_by_home_flag(competitors, False)
    if not home or not away:
        return None

    event_id = str(event.get("id") or "")
    if not event_id:
        return None

    status = _normalize_status(event.get("status") or {})
    status_detail = _status_detail(event.get("status") or {})
    venue = event.get("vnue") or event.get("venue") or {}
    address = venue.get("address") or {}

    return EspnLiveMatch(
        espn_event_id=event_id,
        source_url=urljoin(ESPN_BASE_URL, event.get("link") or f"/soccer/match/_/gameId/{event_id}"),
        home_team=_team_name(home),
        away_team=_team_name(away),
        match_date=_parse_datetime(event.get("date") or event.get("intlDate")),
        status=status,
        status_detail=status_detail,
        home_score=_parse_score(home.get("score")),
        away_score=_parse_score(away.get("score")),
        home_penalty_score=_parse_penalty_score(home),
        away_penalty_score=_parse_penalty_score(away),
        minute=_parse_minute((event.get("status") or {}).get("detail")),
        winner_team=_winner_team_name(home, away),
        stadium=venue.get("fullName"),
        city=address.get("city"),
        home_flag_url=home.get("logo"),
        away_flag_url=away.get("logo"),
        events=_parse_goal_events(home, away),
    )


def _competitor_by_home_flag(competitors: list[dict], is_home: bool) -> dict | None:
    for competitor in competitors:
        if competitor.get("isHome") is is_home:
            return competitor
    return None


def _team_name(competitor: dict) -> str:
    return competitor.get("displayName") or competitor.get("shortDisplayName") or competitor.get("location")


def _winner_team_name(home: dict, away: dict) -> str | None:
    if home.get("winner") is True:
        return _team_name(home)
    if away.get("winner") is True:
        return _team_name(away)
    return None


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        raise ParserError("ESPN event without date")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_score(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_penalty_score(competitor: dict) -> int | None:
    for key in ("shootoutScore", "penaltyScore", "penalties", "pkScore"):
        parsed = _parse_score(competitor.get(key))
        if parsed is not None:
            return parsed

    shootout = competitor.get("shootout")
    if isinstance(shootout, dict):
        for key in ("score", "made", "goals"):
            parsed = _parse_score(shootout.get(key))
            if parsed is not None:
                return parsed
    return None


def _parse_minute(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{1,3})(?:'|\+|$)", value)
    return int(match.group(1)) if match else None


def _parse_goal_events(home: dict, away: dict) -> list[dict]:
    events: list[dict] = []
    for competitor in (home, away):
        team_name = _team_name(competitor)
        for goal in competitor.get("goals") or []:
            minute, extra_minute = _parse_event_minute(goal.get("clock"))
            events.append(
                {
                    "team_name": team_name,
                    "player_name": goal.get("name"),
                    "event_type": "GOAL",
                    "minute": minute,
                    "extra_minute": extra_minute,
                }
            )
    return sorted(events, key=lambda item: ((item["minute"] or 0), (item["extra_minute"] or 0)))


def _parse_event_minute(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    match = re.search(r"(\d{1,3})(?:'\s*)?(?:\+(\d{1,2}))?", value)
    if not match:
        return None, None
    minute = int(match.group(1))
    extra_minute = int(match.group(2)) if match.group(2) else None
    return minute, extra_minute


def _normalize_status(status: dict) -> MatchStatus:
    state = (status.get("state") or "").lower()
    description = _normalize_status_text(status.get("description"))
    detail = _normalize_status_text(status.get("detail"))

    if state == "pre":
        return MatchStatus.SCHEDULED
    if state == "post":
        return MatchStatus.FINISHED
    if description in {"halftime", "half time", "ht"} or detail in {"halftime", "half time", "ht"}:
        return MatchStatus.HALF_TIME
    combined = f"{description} {detail}"
    if _is_penalty_status(combined):
        return MatchStatus.PENALTIES
    if _is_extra_time_status(combined):
        return MatchStatus.EXTRA_TIME
    if state == "in":
        return MatchStatus.LIVE
    if "postpon" in combined:
        return MatchStatus.POSTPONED
    if "cancel" in combined:
        return MatchStatus.CANCELLED
    return MatchStatus.UNKNOWN


def _normalize_status_text(value: str | None) -> str:
    return re.sub(r"[^a-z]+", " ", (value or "").lower()).strip()


def _status_detail(status: dict) -> str | None:
    description = status.get("description")
    detail = status.get("detail")
    if description and detail and description != detail:
        return f"{description} - {detail}"
    return description or detail


def _is_extra_time_status(value: str) -> bool:
    tokens = value.split()
    return (
        "extra time" in value
        or "et" in tokens
        or "aet" in tokens
        or "e t" in value
        or "extra" in tokens
    )


def _is_penalty_status(value: str) -> bool:
    return (
        "penalty" in value
        or "penalties" in value
        or "penalty shootout" in value
        or "shootout" in value
        or "pens" in value.split()
        or "pks" in value.split()
    )
