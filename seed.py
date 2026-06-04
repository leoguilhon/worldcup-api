from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models.match import Match, MatchStatus, ScrapeStatus
from app.models.match_event import MatchEvent
from app.models.team import Team


def get_or_create_team(db, name: str, country_code: str) -> Team:
    team = db.query(Team).filter(Team.name == name).one_or_none()
    if team:
        return team
    team = Team(name=name, country_code=country_code)
    db.add(team)
    db.flush()
    return team


def main() -> None:
    with SessionLocal() as db:
        brazil = get_or_create_team(db, "Brazil", "BR")
        serbia = get_or_create_team(db, "Serbia", "RS")
        portugal = get_or_create_team(db, "Portugal", "PT")
        ghana = get_or_create_team(db, "Ghana", "GH")

        now = datetime.now(timezone.utc)
        matches = [
            Match(
                external_id="mock-001",
                source_url="https://example.com/world-cup/matches/mock-001",
                home_team=brazil,
                away_team=serbia,
                stadium="Lusail Stadium",
                city="Lusail",
                group_name="G",
                stage="Group Stage",
                match_date=now - timedelta(days=1),
                status=MatchStatus.FINISHED,
                home_score=2,
                away_score=0,
                winner_team=brazil,
                last_scraped_at=now,
                scrape_status=ScrapeStatus.SUCCESS,
            ),
            Match(
                external_id="mock-002",
                source_url="https://example.com/world-cup/matches/mock-002",
                home_team=portugal,
                away_team=ghana,
                stadium="Stadium 974",
                city="Doha",
                group_name="H",
                stage="Group Stage",
                match_date=now,
                status=MatchStatus.LIVE,
                home_score=1,
                away_score=1,
                minute=67,
                last_scraped_at=now,
                scrape_status=ScrapeStatus.SUCCESS,
            ),
        ]

        for match in matches:
            existing = db.query(Match).filter(Match.external_id == match.external_id).one_or_none()
            if not existing:
                db.add(match)

        db.flush()
        live = db.query(Match).filter(Match.external_id == "mock-002").one()
        if not live.events:
            live.events.extend(
                [
                    MatchEvent(match=live, team=portugal, player_name="Cristiano Ronaldo", event_type="GOAL", minute=35),
                    MatchEvent(match=live, team=ghana, player_name="Andre Ayew", event_type="GOAL", minute=62),
                ]
            )

        db.commit()
        print("Seed data inserted")


if __name__ == "__main__":
    main()
