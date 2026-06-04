import logging

from app.config import get_settings
from app.services.providers.espn_worldcup import parse_espn_scoreboard_html
from app.utils.http_client import ScraperHttpClient


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    html = ScraperHttpClient().get(settings.espn_test_scoreboard_url)
    matches = parse_espn_scoreboard_html(html)
    match = next((item for item in matches if item.espn_event_id == settings.espn_test_event_id), None)
    if not match:
        raise RuntimeError(
            f"ESPN event {settings.espn_test_event_id} not found in {settings.espn_test_scoreboard_url}"
        )

    logger.info("ESPN event found")
    logger.info("event_id=%s", match.espn_event_id)
    logger.info("source_url=%s", match.source_url)
    logger.info("match=%s vs %s", match.home_team, match.away_team)
    logger.info("match_date=%s", match.match_date.isoformat())
    logger.info("status=%s", match.status.value)
    logger.info("score=%s-%s", match.home_score, match.away_score)
    logger.info("minute=%s", match.minute)
    logger.info("stadium=%s city=%s", match.stadium, match.city)


if __name__ == "__main__":
    main()
