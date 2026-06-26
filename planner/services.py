import asyncio
from collections.abc import Iterable, Mapping
from pathlib import Path

from neko.cache import RollCache
from neko.godfat import BannerRolls
from neko.scraper import ScrapeResult, scrape_active, scrape_catalogue
from planner.models import Banner, Cat

_CACHE = RollCache(Path("rollcache"))

RARITY_ORDER = ["Normal", "Rare", "Super Rare", "Uber Super Rare", "Legend Rare"]


def fetch_banners(seed: int) -> ScrapeResult:
    """Scrape the active banners for a seed (blocking wrapper around the async scraper)."""
    return asyncio.run(scrape_active(seed, cache=_CACHE))


def fetch_catalogue(seed: int) -> ScrapeResult:
    """Scrape every banner for a seed (blocking wrapper), to broaden the catalogue."""
    return asyncio.run(scrape_catalogue(seed, cache=_CACHE))


def group_cats(cats: Iterable[Cat], by: str = "banner") -> list[tuple[str, list[Cat]]]:
    """Section the collection into (heading, cats) pairs, grouped by banner or rarity."""
    groups: dict[str, list[Cat]] = {}
    if by == "rarity":
        for cat in cats:
            groups.setdefault(cat.rarity or "Unknown", []).append(cat)
        rank = {name: i for i, name in enumerate(RARITY_ORDER)}
        return sorted(groups.items(), key=lambda kv: (rank.get(kv[0], len(rank)), kv[0]))

    other: list[Cat] = []
    for cat in cats:
        banner_names = [banner.name for banner in cat.banners.all()]
        for name in banner_names:
            groups.setdefault(name, []).append(cat)
        if not banner_names:
            other.append(cat)
    grouped = sorted(groups.items())
    if other:
        grouped.append(("Other", other))
    return grouped


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
