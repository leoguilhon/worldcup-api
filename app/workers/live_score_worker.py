import logging
import time

from app.config import get_settings
from app.database import SessionLocal
from app.services.scraper_service import ScraperService, has_active_matches
from app.services.worker_heartbeat_service import touch_worker_heartbeat


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def run_worker() -> None:
    settings = get_settings()
    scraper = ScraperService()
    last_schedule_scrape = 0.0
    last_friendly_discovery = 0.0

    logger.info("Starting WorldCup API worker")
    while True:
        started = time.monotonic()
        with SessionLocal() as db:
            touch_worker_heartbeat(db, "live_score_worker")
            scraper.scrape_live_matches(db)
            live_now = has_active_matches(db)

            if not live_now and started - last_schedule_scrape >= settings.schedule_scrape_interval_hours * 3600:
                scraper.scrape_schedule(db)
                last_schedule_scrape = started

            if not live_now and started - last_friendly_discovery >= settings.friendly_discovery_interval_hours * 3600:
                scraper.discover_espn_friendlies(db)
                last_friendly_discovery = started

        elapsed = time.monotonic() - started
        sleep_for = max(settings.live_scrape_interval_seconds - elapsed, 1)
        logger.info("Worker cycle finished in %.1fs. Sleeping %.1fs", elapsed, sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    run_worker()
