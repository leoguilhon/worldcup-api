import re
from datetime import datetime, timedelta, timezone, tzinfo
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.models.match import MatchStatus
from app.services.scraper_service import ParserError, ScrapedMatch


SOURCE_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup"


def parse_wikipedia_2026_schedule(html: str, source_url: str = SOURCE_URL) -> list[ScrapedMatch]:
    soup = BeautifulSoup(html, "html.parser")
    boxes = soup.select("div.footballbox")
    if not boxes:
        raise ParserError("No footballbox blocks found in Wikipedia page")

    matches = []
    for box in boxes:
        score_cell = box.select_one(".fscore")
        score_link = score_cell.select_one("a") if score_cell else None
        match_number = _match_number(score_cell.get_text(" ", strip=True) if score_cell else "")
        if not match_number:
            continue

        home_name = _team_name(box, ".fhome")
        away_name = _team_name(box, ".faway")
        if not home_name or not away_name:
            continue

        match_url = urljoin(source_url, score_link.get("href")) if score_link and score_link.get("href") else source_url
        group_name, stage = _group_and_stage(box, score_link)
        stadium, city = _venue(box)
        home_score, away_score = _score(score_cell)

        matches.append(
            ScrapedMatch(
                external_id=f"wikipedia-2026-match-{match_number:03d}",
                source_url=match_url,
                home_team=home_name,
                away_team=away_name,
                match_date=_match_datetime(box),
                home_flag_url=_flag_url(box, ".fhome", source_url),
                away_flag_url=_flag_url(box, ".faway", source_url),
                stadium=stadium,
                city=city,
                group_name=group_name,
                stage=stage,
                status=MatchStatus.FINISHED if home_score is not None and away_score is not None else MatchStatus.SCHEDULED,
                home_score=home_score,
                away_score=away_score,
                minute=None,
                events=[],
            )
        )

    if not matches:
        raise ParserError("No valid matches parsed from Wikipedia page")

    return sorted(matches, key=lambda item: item.match_date)


def _team_name(box, selector: str) -> str | None:
    cell = box.select_one(selector)
    if not cell:
        return None
    link = cell.select_one('span[itemprop="name"] > a')
    if not link:
        link = cell.select_one("a")
    return link.get_text(" ", strip=True) if link else cell.get_text(" ", strip=True)


def _flag_url(box, selector: str, source_url: str) -> str | None:
    img = box.select_one(f"{selector} img")
    if not img:
        return None
    src = img.get("src")
    if not src:
        return None
    return urljoin(source_url, src)


def _match_number(text: str) -> int | None:
    match = re.search(r"\bMatch\s+(\d{1,3})\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _match_datetime(box) -> datetime:
    date_node = box.select_one(".dtstart")
    time_node = box.select_one(".ftime")
    if not date_node or not time_node:
        raise ParserError("Match block without date or time")

    date_value = date_node.get_text(strip=True)
    time_text = time_node.get_text(" ", strip=True).replace("\xa0", " ")
    time_match = re.search(r"(\d{1,2}):(\d{2})\s*([ap])\.m\.", time_text, re.IGNORECASE)
    if not time_match:
        raise ParserError(f"Invalid match time: {time_text}")

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    period = time_match.group(3).lower()
    if period == "p" and hour != 12:
        hour += 12
    if period == "a" and hour == 12:
        hour = 0

    tz_node = time_node.select_one("a[title^='UTC']")
    offset = _parse_utc_offset(tz_node.get("title") if tz_node else time_text)
    local_dt = datetime.fromisoformat(date_value).replace(hour=hour, minute=minute, tzinfo=offset)
    return local_dt.astimezone(timezone.utc)


def _parse_utc_offset(value: str) -> tzinfo:
    match = re.search(r"UTC\s*([+\-−])\s*(\d{1,2})(?::?(\d{2}))?", value)
    if not match:
        return timezone.utc
    sign = -1 if match.group(1) in ("-", "−") else 1
    hours = int(match.group(2))
    minutes = int(match.group(3) or 0)
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _venue(box) -> tuple[str | None, str | None]:
    links = box.select(".fright [itemprop='name address'] a")
    if len(links) >= 2:
        return links[0].get_text(" ", strip=True), links[1].get_text(" ", strip=True)
    text = box.select_one(".fright")
    if not text:
        return None, None
    parts = [part.strip() for part in text.get_text(" ", strip=True).split(",", 1)]
    return (parts[0] or None, parts[1] if len(parts) > 1 else None)


def _score(score_cell) -> tuple[int | None, int | None]:
    if not score_cell:
        return None, None
    text = score_cell.get_text(" ", strip=True)
    match = re.search(r"\b(\d{1,2})\s*[–-]\s*(\d{1,2})\b", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _group_and_stage(box, score_link) -> tuple[str | None, str | None]:
    title = score_link.get("title", "") if score_link else ""
    group_match = re.search(r"Group\s+([A-L])", title)
    if group_match:
        return group_match.group(1), "Group Stage"

    heading = box.find_previous(["h2", "h3", "h4"])
    heading_text = heading.get_text(" ", strip=True) if heading else ""
    if re.search(r"Round of 32", heading_text, re.IGNORECASE):
        return None, "Round of 32"
    if re.search(r"Round of 16", heading_text, re.IGNORECASE):
        return None, "Round of 16"
    if re.search(r"Quarterfinal", heading_text, re.IGNORECASE):
        return None, "Quarterfinals"
    if re.search(r"Semifinal", heading_text, re.IGNORECASE):
        return None, "Semifinals"
    if re.search(r"third place", heading_text, re.IGNORECASE):
        return None, "Third Place"
    if re.search(r"Final", heading_text, re.IGNORECASE):
        return None, "Final"
    return None, "Knockout Stage"
