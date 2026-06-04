import logging
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from app.config import get_settings


logger = logging.getLogger(__name__)


class ScraperHttpClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._last_request_at = 0.0
        self._robots_cache: dict[str, RobotFileParser] = {}

    def get(self, url: str) -> str:
        if not self._can_fetch(url):
            raise PermissionError(f"robots.txt does not allow scraping this URL: {url}")

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self._sleep_until_allowed()
                headers = {"User-Agent": self.settings.scraper_user_agent}
                self._last_request_at = time.monotonic()
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=self.settings.scraper_timeout_seconds,
                )
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                backoff = 2**attempt
                logger.warning("HTTP error fetching %s: %s. Backing off %ss", url, exc, backoff)
                time.sleep(backoff)

        raise RuntimeError(f"Failed to fetch {url}") from last_error

    def _sleep_until_allowed(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        min_interval = self.settings.scraper_min_request_interval_seconds
        if elapsed < min_interval:
            sleep_for = min_interval - elapsed
            logger.info("Respecting crawl delay: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)

    def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots_cache.get(origin)
        if not parser:
            parser = RobotFileParser()
            robots_url = urljoin(origin, "/robots.txt")
            parser.set_url(robots_url)
            try:
                self._sleep_until_allowed()
                self._last_request_at = time.monotonic()
                response = requests.get(
                    robots_url,
                    headers={"User-Agent": self.settings.scraper_user_agent},
                    timeout=self.settings.scraper_timeout_seconds,
                )
                if response.status_code == 404:
                    parser.parse([])
                else:
                    response.raise_for_status()
                    parser.parse(response.text.splitlines())
            except requests.RequestException:
                logger.warning("Could not read robots.txt from %s; skipping fetch for caution", origin)
                return False
            self._robots_cache[origin] = parser

        return parser.can_fetch(self.settings.scraper_user_agent, url)
