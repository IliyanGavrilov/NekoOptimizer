# Cat and material icons come from battlecatsinfo's image repo (GitHub Pages,
# CORS-open). Fetching them once lets the site serve its own copies instead of
# hotlinking a third party.

import urllib.error
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings

from neko.bcdata import _get, load_records
from neko.gamedata import load_cannons, load_evolve
from neko.region import CODES

SOURCE = "https://battlecatsinfo.github.io/img/u/{unit_id}/{form}.png"
ITEM_SOURCE = "https://battlecatsinfo.github.io/img/r/{item_id}.png"
# settings serves these instead of hotlinking once they exist
ICONS_DIR = settings.ICONS_DIR
ITEMS_DIR = settings.ITEMS_DIR
_WORKERS = 8


def wanted(records: Iterable[Mapping]) -> set[tuple[int, int]]:
    """Every (unit id, form index) pair the catalogue can show an icon for."""
    return {(record["id"], form) for record in records for form in range(len(record["forms"]))}


def catalogue_icons() -> set[tuple[int, int]]:
    """The pairs across every region's committed catalogue - unit ids are shared, but a
    version can be a form ahead."""
    return set().union(*(wanted(load_records(region)) for region in CODES))


def catalogue_materials() -> set[int]:
    """Every item id the resources page can put an icon next to: the evolution
    materials, the castle recipes' materials and their Z versions, over all regions."""
    items = set()
    for region in CODES:
        for cost in load_evolve(region)["units"].values():
            for form in cost.values():
                if form:
                    items.update(item_id for item_id, _ in form["items"])
        cannons = load_cannons(region)
        items.update(cannons["materials"])
        items.update(cannons["zmaterials"])

    return items


def fetch(unit_id: int, form: int, root: Path = ICONS_DIR) -> bool:
    """Save one icon under *root*, skipping one already there (network). False when the
    source has no such form."""
    path = root / str(unit_id) / f"{form}.png"
    if path.exists():
        return True

    try:
        data = _get(SOURCE.format(unit_id=unit_id, form=form))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

    return True


def fetch_item(item_id: int, root: Path = ITEMS_DIR) -> bool:
    """Save one material's icon under *root*, skipping one already there (network).
    False when the source has no icon for it (Engineers, for one)."""
    path = root / f"{item_id}.png"
    if path.exists():
        return True

    try:
        data = _get(ITEM_SOURCE.format(item_id=item_id))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

    return True


def _download(job, items: Iterable, workers: int) -> tuple[int, int]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        got = list(pool.map(job, sorted(items)))

    return sum(got), len(got) - sum(got)


def refresh(
    icons: Iterable[tuple[int, int]] | None = None,
    root: Path = ICONS_DIR,
    workers: int = _WORKERS,
) -> tuple[int, int]:
    """Download every catalogue icon not already under *root* (network); returns how many
    are in place and how many the source doesn't publish. Re-runs only fetch what's new."""
    icons = catalogue_icons() if icons is None else icons

    return _download(lambda pair: fetch(*pair, root=root), icons, workers)


def refresh_items(
    items: Iterable[int] | None = None,
    root: Path = ITEMS_DIR,
    workers: int = _WORKERS,
) -> tuple[int, int]:
    """The same for the grind materials' icons."""
    items = catalogue_materials() if items is None else items

    return _download(lambda item_id: fetch_item(item_id, root=root), items, workers)
