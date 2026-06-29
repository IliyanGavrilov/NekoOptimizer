import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode

import aiohttp

from neko.cache import RollCache
from neko.gacha import multi_configs
from neko.godfat import (
    BannerRolls,
    GachaEvent,
    parse_events,
    parse_guaranteed,
    parse_rerolls,
    parse_rolls,
)
from neko.search import Multi

BASE_URL = "https://bc.godfat.org/"
DEFAULT_COUNT = 100

Fetcher = Callable[[str], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class ScrapeResult:
    """The active banners' rolls plus each banner's matched multi-roll options."""

    banners: dict[str, BannerRolls]
    multis: dict[str, tuple[Multi, ...]]
    dates: dict[str, tuple[date, date]] = field(default_factory=dict)


def roll_url(seed: int, event: str, count: int = DEFAULT_COUNT, guaranteed: bool = False) -> str:
    query = {"seed": seed, "event": event, "count": count, "display": "text", "name": 0}
    if guaranteed:
        query["force_guaranteed"] = 1
    return f"{BASE_URL}?{urlencode(query)}"


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


def latest_events(events: Iterable[GachaEvent], names: Iterable[str]) -> list[GachaEvent]:
    """The most recent run of each named banner (a name can recur over time)."""
    names = set(names)
    chosen: dict[str, GachaEvent] = {}
    for event in events:
        if event.name not in names:
            continue
        current = chosen.get(event.name)
        if current is None or event.start > current.start:
            chosen[event.name] = event
    return list(chosen.values())


class GodfatScraper:
    """Fetch and parse banners through an injected fetcher, with optional caching."""

    def __init__(self, fetch: Fetcher, cache: RollCache | None = None, count: int = DEFAULT_COUNT):
        self._fetch = fetch
        self._cache = cache
        self._count = count

    async def events(self) -> list[GachaEvent]:
        return parse_events(await self._fetch(BASE_URL))

    async def rolls(self, seed: int, event: str) -> BannerRolls:
        if self._cache is not None:
            hit = self._cache.load(seed, event, self._count)
            if hit is not None:
                return hit
        html = await self._fetch(roll_url(seed, event, self._count, guaranteed=True))
        rolls = BannerRolls(parse_rolls(html), parse_guaranteed(html), parse_rerolls(html))
        if self._cache is not None:
            self._cache.save(seed, event, self._count, rolls)
        return rolls

    async def all_rolls(self, seed: int, events: Iterable[str]) -> dict[str, BannerRolls]:
        events = list(events)
        results = await asyncio.gather(
            *(self.rolls(seed, event) for event in events), return_exceptions=True
        )
        # godfat occasionally 500s on individual banners; skip those, keep the rest.
        return {
            event: rolls
            for event, rolls in zip(events, results, strict=True)
            if not isinstance(rolls, Exception)
        }


async def build_result(
    scraper: GodfatScraper, seed: int, events: Iterable[GachaEvent]
) -> ScrapeResult:
    """Roll the given events and key them by banner name (recurring re-runs collapse)."""
    events = list(events)
    rolls = await scraper.all_rolls(seed, [event.event_id for event in events])
    configs = multi_configs(events)
    banners = {event.name: rolls[event.event_id] for event in events if event.event_id in rolls}
    multis = {
        event.name: configs[event.event_id]
        for event in events
        if event.event_id in configs and event.event_id in rolls
    }
    # A banner name can recur; keep its most recent run's dates.
    dates: dict[str, tuple[date, date]] = {}
    for event in events:
        if event.event_id not in rolls:
            continue
        current = dates.get(event.name)
        if current is None or event.start > current[0]:
            dates[event.name] = (event.start, event.end)
    return ScrapeResult(banners, multis, dates)


async def scrape_active(
    seed: int,
    *,
    count: int = DEFAULT_COUNT,
    cache: RollCache | None = None,
    today: date | None = None,
) -> ScrapeResult:
    async with aiohttp.ClientSession() as session:
        scraper = GodfatScraper(make_fetcher(session), cache, count)
        active = active_events(await scraper.events(), today)
        return await build_result(scraper, seed, active)


async def scrape_catalogue(
    seed: int, *, count: int = DEFAULT_COUNT, cache: RollCache | None = None
) -> ScrapeResult:
    """Scrape every banner in the dropdown, not just the active ones, to broaden the catalogue."""
    async with aiohttp.ClientSession() as session:
        scraper = GodfatScraper(make_fetcher(session), cache, count)
        return await build_result(scraper, seed, await scraper.events())


async def scrape_selected(
    seed: int,
    names: Iterable[str],
    *,
    count: int = DEFAULT_COUNT,
    cache: RollCache | None = None,
) -> ScrapeResult:
    """Roll only the named banners (their most recent run) for a chosen session."""
    async with aiohttp.ClientSession() as session:
        scraper = GodfatScraper(make_fetcher(session), cache, count)
        chosen = latest_events(await scraper.events(), names)
        return await build_result(scraper, seed, chosen)
