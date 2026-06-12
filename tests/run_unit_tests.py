from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.match import Match, MatchCompetition, MatchStatus
from app.models.scrape_run import ScrapeRun, ScrapeRunStatus
from app.models.team import Team
from app.models.worker_heartbeat import WorkerHeartbeat
from app.services.match_service import get_group_standings, get_groups, get_live_matches, get_matches
from app.services.providers.espn_worldcup import parse_espn_scoreboard_html
from app.services.scraping_status_service import get_scraping_status
from app.services.scraper_service import (
    expire_stale_active_matches,
    get_espn_scoreboard_targets,
    get_or_create_team,
    is_friendly_for_tracked_team,
    upsert_espn_friendly,
)


def test_espn_parser() -> None:
    html = Path("tests/fixtures/espn_scoreboard_mock.html").read_text(encoding="utf-8")
    matches = parse_espn_scoreboard_html(html)
    by_id = {match.espn_event_id: match for match in matches}

    assert len(matches) == 7
    assert by_id["mock-pre"].status == MatchStatus.SCHEDULED
    assert by_id["mock-live"].status == MatchStatus.LIVE
    assert by_id["mock-live"].home_team == "Brazil"
    assert by_id["mock-live"].away_team == "Haiti"
    assert by_id["mock-live"].home_score == 2
    assert by_id["mock-live"].away_score == 1
    assert by_id["mock-live"].minute == 67
    assert [event["player_name"] for event in by_id["mock-live"].events] == ["Vini Jr.", "D. Etienne", "Rodrygo"]
    assert by_id["mock-live"].events[-1]["minute"] == 45
    assert by_id["mock-live"].events[-1]["extra_minute"] == 2
    assert by_id["mock-half"].status == MatchStatus.HALF_TIME
    assert by_id["mock-post"].status == MatchStatus.FINISHED
    assert by_id["mock-second-half"].status == MatchStatus.LIVE
    assert by_id["mock-second-half"].minute == 71
    assert by_id["mock-extra-time"].status == MatchStatus.EXTRA_TIME
    assert by_id["mock-extra-time"].status_detail == "Extra Time - 105'"
    assert by_id["mock-extra-time"].minute == 105
    assert by_id["mock-penalties"].status == MatchStatus.PENALTIES
    assert by_id["mock-penalties"].status_detail == "Penalty Shootout - Penalties"
    assert by_id["mock-penalties"].home_penalty_score == 5
    assert by_id["mock-penalties"].away_penalty_score == 4
    assert by_id["mock-penalties"].winner_team == "Spain"


def test_country_codes_and_placeholders() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        brazil = get_or_create_team(db, "Brazil")
        placeholder = get_or_create_team(db, "Winner Group A")
        assert brazil.country_code == "BR"
        assert brazil.is_placeholder is False
        assert placeholder.country_code is None
        assert placeholder.is_placeholder is True


def test_group_standings() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        brazil = Team(name="Brazil", country_code="BR")
        haiti = Team(name="Haiti", country_code="HT")
        scotland = Team(name="Scotland", country_code="SCT")
        morocco = Team(name="Morocco", country_code="MA")
        db.add_all([brazil, haiti, scotland, morocco])
        db.flush()

        db.add_all(
            [
                Match(
                    external_id="test-1",
                    source_url="https://example.com/test-1",
                    home_team=brazil,
                    away_team=haiti,
                    group_name="C",
                    stage="Group Stage",
                    match_date=datetime(2026, 6, 19, tzinfo=timezone.utc),
                    status=MatchStatus.FINISHED,
                    home_score=2,
                    away_score=1,
                ),
                Match(
                    external_id="test-2",
                    source_url="https://example.com/test-2",
                    home_team=scotland,
                    away_team=morocco,
                    group_name="C",
                    stage="Group Stage",
                    match_date=datetime(2026, 6, 19, 2, tzinfo=timezone.utc),
                    status=MatchStatus.FINISHED,
                    home_score=0,
                    away_score=0,
                ),
            ]
        )
        db.commit()

        standings = get_group_standings(db, "C")
        assert [row.team.name for row in standings] == ["Brazil", "Scotland", "Morocco", "Haiti"]
        assert standings[0].points == 3
        assert standings[0].goals_for == 2
        assert standings[-1].points == 0


def test_group_standings_include_scheduled_teams() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        teams = [
            Team(name="Mexico", country_code="MX"),
            Team(name="South Africa", country_code="ZA"),
            Team(name="South Korea", country_code="KR"),
            Team(name="Spain", country_code="ES"),
        ]
        db.add_all(teams)
        db.flush()
        db.add_all(
            [
                Match(
                    external_id="scheduled-1",
                    competition=MatchCompetition.WORLD_CUP,
                    source_url="https://example.com/scheduled-1",
                    home_team=teams[0],
                    away_team=teams[1],
                    group_name="A",
                    stage="Group Stage",
                    match_date=datetime(2026, 6, 11, tzinfo=timezone.utc),
                    status=MatchStatus.SCHEDULED,
                ),
                Match(
                    external_id="scheduled-2",
                    competition=MatchCompetition.WORLD_CUP,
                    source_url="https://example.com/scheduled-2",
                    home_team=teams[2],
                    away_team=teams[3],
                    group_name="A",
                    stage="Group Stage",
                    match_date=datetime(2026, 6, 12, tzinfo=timezone.utc),
                    status=MatchStatus.SCHEDULED,
                ),
            ]
        )
        db.commit()

        standings = get_group_standings(db, "A")
        assert {row.team.name for row in standings} == {"Mexico", "South Africa", "South Korea", "Spain"}
        assert all(row.played == 0 for row in standings)
        assert all(row.points == 0 for row in standings)


def test_group_standings_only_use_group_stage_matches() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        teams = [
            Team(name="Mexico", country_code="MX"),
            Team(name="South Africa", country_code="ZA"),
            Team(name="France", country_code="FR"),
            Team(name="Germany", country_code="DE"),
        ]
        db.add_all(teams)
        db.flush()
        db.add_all(
            [
                Match(
                    external_id="group-stage",
                    competition=MatchCompetition.WORLD_CUP,
                    source_url="https://example.com/group-stage",
                    home_team=teams[0],
                    away_team=teams[1],
                    group_name="A",
                    stage="Group Stage",
                    match_date=datetime(2026, 6, 11, tzinfo=timezone.utc),
                    status=MatchStatus.FINISHED,
                    home_score=1,
                    away_score=0,
                ),
                Match(
                    external_id="bad-knockout-group",
                    competition=MatchCompetition.WORLD_CUP,
                    source_url="https://example.com/bad-knockout-group",
                    home_team=teams[2],
                    away_team=teams[3],
                    group_name="A",
                    stage="Round of 32",
                    match_date=datetime(2026, 6, 29, tzinfo=timezone.utc),
                    status=MatchStatus.FINISHED,
                    home_score=4,
                    away_score=0,
                ),
                Match(
                    external_id="bad-knockout-only",
                    competition=MatchCompetition.WORLD_CUP,
                    source_url="https://example.com/bad-knockout-only",
                    home_team=teams[2],
                    away_team=teams[3],
                    group_name="Z",
                    stage="Round of 16",
                    match_date=datetime(2026, 7, 4, tzinfo=timezone.utc),
                    status=MatchStatus.FINISHED,
                    home_score=2,
                    away_score=1,
                ),
            ]
        )
        db.commit()

        standings = get_group_standings(db, "A")
        assert [row.team.name for row in standings] == ["Mexico", "South Africa"]
        assert get_groups(db) == ["A"]


def test_friendly_tracking_upsert() -> None:
    html = Path("tests/fixtures/espn_scoreboard_mock.html").read_text(encoding="utf-8")
    update = next(match for match in parse_espn_scoreboard_html(html) if match.espn_event_id == "mock-live")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        tracked_team = get_or_create_team(db, "Brazil")
        db.commit()

        assert is_friendly_for_tracked_team(update, {"brazil"})
        match = upsert_espn_friendly(db, update)
        db.commit()

        assert match.competition == MatchCompetition.FRIENDLY
        assert match.espn_event_id == "mock-live"
        assert match.external_id == "espn-friendly-mock-live"
        assert match.home_team_id == tracked_team.id
        assert match.status == MatchStatus.LIVE
        assert match.home_score == 2
        assert match.away_score == 1


def test_espn_targets_use_candidate_competition() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        brazil = get_or_create_team(db, "Brazil")
        mali = get_or_create_team(db, "Mali")
        db.add(
            Match(
                external_id="friendly-live",
                espn_event_id="friendly-live",
                competition=MatchCompetition.FRIENDLY,
                source_url="https://example.com/friendly-live",
                home_team=brazil,
                away_team=mali,
                stage="Friendly",
                match_date=datetime.now(timezone.utc),
                status=MatchStatus.LIVE,
                home_score=1,
                away_score=0,
            )
        )
        db.commit()

        targets = get_espn_scoreboard_targets(
            db,
            before_minutes=180,
            after_minutes=240,
            worldcup_base_url="https://example.com/worldcup",
            friendly_base_url="https://example.com/friendly",
            include_friendlies=True,
        )

        assert targets == [(datetime.now(timezone.utc).date(), "https://example.com/friendly")]


def test_live_matches_ignore_stale_active_status() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        home = get_or_create_team(db, "Argentina")
        away = get_or_create_team(db, "Honduras")
        db.add_all(
            [
                Match(
                    external_id="stale-live",
                    source_url="https://example.com/stale-live",
                    home_team=home,
                    away_team=away,
                    match_date=now - timedelta(days=4),
                    status=MatchStatus.LIVE,
                    status_detail="First Half - 1'",
                    minute=1,
                    last_scraped_at=now - timedelta(days=4),
                ),
                Match(
                    external_id="current-live",
                    source_url="https://example.com/current-live",
                    home_team=home,
                    away_team=away,
                    match_date=now,
                    status=MatchStatus.LIVE,
                    status_detail="First Half - 12'",
                    minute=12,
                    last_scraped_at=now,
                ),
            ]
        )
        db.commit()

        assert [match.external_id for match in get_live_matches(db)] == ["current-live"]
        assert [match.external_id for match in get_matches(db, status=MatchStatus.LIVE)] == ["current-live"]


def test_expire_stale_active_matches_marks_unknown() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        home = get_or_create_team(db, "Argentina")
        away = get_or_create_team(db, "Honduras")
        stale = Match(
            external_id="stale-live",
            source_url="https://example.com/stale-live",
            home_team=home,
            away_team=away,
            match_date=now - timedelta(hours=5),
            status=MatchStatus.LIVE,
            status_detail="First Half - 1'",
            minute=1,
            last_scraped_at=now - timedelta(hours=5),
        )
        current = Match(
            external_id="current-live",
            source_url="https://example.com/current-live",
            home_team=home,
            away_team=away,
            match_date=now,
            status=MatchStatus.LIVE,
            status_detail="First Half - 12'",
            minute=12,
            last_scraped_at=now,
        )
        db.add_all([stale, current])
        db.commit()

        assert expire_stale_active_matches(db, after_minutes=240) == 1
        assert stale.status == MatchStatus.UNKNOWN
        assert stale.status_detail == "Stale live status expired"
        assert stale.minute is None
        assert current.status == MatchStatus.LIVE


def test_scraping_status_with_heartbeat_and_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(WorkerHeartbeat(name="live_score_worker", last_seen_at=now))
        db.add(
            ScrapeRun(
                source="espn_scoreboard:test",
                status=ScrapeRunStatus.SUCCESS,
                started_at=now,
                finished_at=now,
                parsed_count=1,
                applied_count=1,
            )
        )
        db.commit()

        status = get_scraping_status(db)
        assert status.status == "ok"
        assert status.worker_status == "ok"
        assert status.last_run is not None
        assert status.last_run.source == "espn_scoreboard:test"


def main() -> None:
    test_espn_parser()
    test_country_codes_and_placeholders()
    test_group_standings()
    test_group_standings_include_scheduled_teams()
    test_group_standings_only_use_group_stage_matches()
    test_friendly_tracking_upsert()
    test_espn_targets_use_candidate_competition()
    test_live_matches_ignore_stale_active_status()
    test_expire_stale_active_matches_marks_unknown()
    test_scraping_status_with_heartbeat_and_run()
    print("unit tests passed")


if __name__ == "__main__":
    main()
