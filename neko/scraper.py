import asyncio
from collections.abc import Awaitable, Callable, Iterable
from datetime import date
from urllib.parse import urlencode

import aiohttp

from neko.cache import RollCache
from neko.godfat import GachaEvent, TrackPull, parse_events, parse_rolls

BASE_URL = "https://bc.godfat.org/"
DEFAULT_COUNT = 100

Fetcher = Callable[[str], Awaitable[str]]


def roll_url(seed: int, event: str, count: int = DEFAULT_COUNT) -> str:
    query = urlencode({"seed": seed, "event": event, "count": count, "display": "text", "name": 2})
    return f"{BASE_URL}?{query}"


async def aiohttp_fetch(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


def make_fetcher(session: aiohttp.ClientSession) -> Fetcher:
    async def fetch(url: str) -> str:
        return await aiohttp_fetch(session, url)

    return fetch


def active_events(events: Iterable[GachaEvent], today: date | None = None) -> list[GachaEvent]:
    today = today or date.today()
    return [event for event in events if event.start <= today <= event.end]


class GodfatScraper:
    """Fetch and parse banners through an injected fetcher, with optional caching."""

    def __init__(self, fetch: Fetcher, cache: RollCache | None = None, count: int = DEFAULT_COUNT):
        self._fetch = fetch
        self._cache = cache
        self._count = count

    async def events(self) -> list[GachaEvent]:
        return parse_events(await self._fetch(BASE_URL))

    async def rolls(self, seed: int, event: str) -> list[TrackPull]:
        if self._cache is not None:
            hit = self._cache.load(seed, event, self._count)
            if hit is not None:
                return hit
        pulls = parse_rolls(await self._fetch(roll_url(seed, event, self._count)))
        if self._cache is not None:
            self._cache.save(seed, event, self._count, pulls)
        return pulls

    async def all_rolls(self, seed: int, events: Iterable[str]) -> dict[str, list[TrackPull]]:
        events = list(events)
        results = await asyncio.gather(*(self.rolls(seed, event) for event in events))
        return dict(zip(events, results, strict=True))


async def scrape_active(
    seed: int,
    *,
    count: int = DEFAULT_COUNT,
    cache: RollCache | None = None,
    today: date | None = None,
) -> dict[str, list[TrackPull]]:
    async with aiohttp.ClientSession() as session:
        scraper = GodfatScraper(make_fetcher(session), cache, count)
        active = active_events(await scraper.events(), today)
        return await scraper.all_rolls(seed, [event.event_id for event in active])
