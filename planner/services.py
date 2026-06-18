import asyncio
from pathlib import Path

from neko.cache import RollCache
from neko.godfat import TrackPull
from neko.scraper import scrape_active

_CACHE = RollCache(Path("rollcache"))


def fetch_banners(seed: int) -> dict[str, list[TrackPull]]:
    """Scrape the active banners for a seed (blocking wrapper around the async scraper)."""
    return asyncio.run(scrape_active(seed, cache=_CACHE))
