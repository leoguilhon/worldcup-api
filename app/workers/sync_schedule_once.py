import logging

from app.database import SessionLocal
from app.services.scraper_service import ScraperService


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def main() -> None:
    with SessionLocal() as db:
        ScraperService().scrape_schedule(db)


if __name__ == "__main__":
    main()
