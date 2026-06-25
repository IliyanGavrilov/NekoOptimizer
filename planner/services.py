import asyncio
from collections.abc import Mapping
from pathlib import Path

from neko.cache import RollCache
from neko.godfat import BannerRolls
from neko.scraper import ScrapeResult, scrape_active
from planner.models import Banner, Cat

_CACHE = RollCache(Path("rollcache"))


def fetch_banners(seed: int) -> ScrapeResult:
    """Scrape the active banners for a seed (blocking wrapper around the async scraper)."""
    return asyncio.run(scrape_active(seed, cache=_CACHE))


def import_cats(banners: Mapping[str, BannerRolls]) -> int:
    """Add scraped cats and their banner membership to the catalogue; return new-cat count."""
    created = 0
    for banner_name, rolls in banners.items():
        banner, _ = Banner.objects.get_or_create(name=banner_name)
        for pull in (*rolls.pulls, *rolls.guaranteed):
            cat, was_created = Cat.objects.get_or_create(
                name=pull.cat, defaults={"rarity": pull.rarity.value}
            )
            created += int(was_created)
            banner.cats.add(cat)
    return created
