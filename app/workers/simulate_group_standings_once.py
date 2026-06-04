import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.match import Match, MatchStatus
from app.services.match_service import get_group_standings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    with SessionLocal() as db:
        matches = (
            db.query(Match)
            .filter(Match.group_name == "A")
            .order_by(Match.match_date.asc())
            .limit(2)
            .all()
        )
        if len(matches) < 2:
            raise RuntimeError("Group A needs at least two matches to simulate standings")

        snapshots = []
        for match in matches:
            snapshots.append(
                {
                    "match": match,
                    "status": match.status,
                    "home_score": match.home_score,
                    "away_score": match.away_score,
                    "last_scraped_at": match.last_scraped_at,
                }
            )

        matches[0].status = MatchStatus.FINISHED
        matches[0].home_score = 2
        matches[0].away_score = 1
        matches[0].last_scraped_at = datetime.now(timezone.utc)
        matches[1].status = MatchStatus.FINISHED
        matches[1].home_score = 0
        matches[1].away_score = 0
        matches[1].last_scraped_at = datetime.now(timezone.utc)
        db.flush()

        standings = get_group_standings(db, "A")
        for row in standings:
            logger.info(
                "%s Pts=%s P=%s W=%s D=%s L=%s GF=%s GA=%s GD=%s",
                row.team.name,
                row.points,
                row.played,
                row.won,
                row.drawn,
                row.lost,
                row.goals_for,
                row.goals_against,
                row.goal_difference,
            )

        for snapshot in snapshots:
            match = snapshot["match"]
            match.status = snapshot["status"]
            match.home_score = snapshot["home_score"]
            match.away_score = snapshot["away_score"]
            match.last_scraped_at = snapshot["last_scraped_at"]
        db.rollback()
        logger.info("Simulation rolled back; no test data was persisted")


if __name__ == "__main__":
    main()
