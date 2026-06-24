import asyncio
from collections.abc import Mapping
from pathlib import Path

from neko.cache import RollCache
from neko.godfat import BannerRolls
from neko.scraper import scrape_active
from planner.models import Cat

_CACHE = RollCache(Path("rollcache"))


def fetch_banners(seed: int) -> dict[str, BannerRolls]:
    """Scrape the active banners for a seed (blocking wrapper around the async scraper)."""
    return asyncio.run(scrape_active(seed, cache=_CACHE))


def import_cats(banners: Mapping[str, BannerRolls]) -> int:
    """Add any unseen cats from scraped rolls to the catalogue; return how many were new."""
    rarity_by_cat: dict[str, str] = {}
    for rolls in banners.values():
        for pull in (*rolls.pulls, *rolls.guaranteed):
            rarity_by_cat.setdefault(pull.cat, pull.rarity.value)
    created = 0
    for name, rarity in rarity_by_cat.items():
        _, was_created = Cat.objects.get_or_create(name=name, defaults={"rarity": rarity})
        created += int(was_created)
    return created
