import asyncio
from collections.abc import Mapping
from pathlib import Path

from neko.cache import RollCache
from neko.godfat import TrackPull
from neko.scraper import scrape_active
from planner.models import Cat

_CACHE = RollCache(Path("rollcache"))


def fetch_banners(seed: int) -> dict[str, list[TrackPull]]:
    """Scrape the active banners for a seed (blocking wrapper around the async scraper)."""
    return asyncio.run(scrape_active(seed, cache=_CACHE))


def import_cats(pulls_by_banner: Mapping[str, list[TrackPull]]) -> int:
    """Add any unseen cats from scraped pulls to the catalogue; return how many were new."""
    rarity_by_cat: dict[str, str] = {}
    for pulls in pulls_by_banner.values():
        for pull in pulls:
            rarity_by_cat.setdefault(pull.cat, pull.rarity.value)
    created = 0
    for name, rarity in rarity_by_cat.items():
        _, was_created = Cat.objects.get_or_create(name=name, defaults={"rarity": rarity})
        created += int(was_created)
    return created
