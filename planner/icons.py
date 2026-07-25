# Cat icons come from battlecatsinfo's image repo (GitHub Pages, CORS-open). Fetching
# them once lets the site serve its own copies instead of hotlinking a third party.

import urllib.error
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings

from neko.bcdata import _get, load_records
from neko.region import CODES

SOURCE = "https://battlecatsinfo.github.io/img/u/{unit_id}/{form}.png"
ICONS_DIR = settings.ICONS_DIR  # settings serves these instead of hotlinking once it exists
_WORKERS = 8


def wanted(records: Iterable[Mapping]) -> set[tuple[int, int]]:
    """Every (unit id, form index) pair the catalogue can show an icon for."""
    return {(record["id"], form) for record in records for form in range(len(record["forms"]))}


def catalogue_icons() -> set[tuple[int, int]]:
    """The pairs across every region's committed catalogue - unit ids are shared, but a
    version can be a form ahead."""
    return set().union(*(wanted(load_records(region)) for region in CODES))


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


def refresh(
    icons: Iterable[tuple[int, int]] | None = None,
    root: Path = ICONS_DIR,
    workers: int = _WORKERS,
) -> tuple[int, int]:
    """Download every catalogue icon not already under *root* (network); returns how many
    are in place and how many the source doesn't publish. Re-runs only fetch what's new."""
    icons = sorted(catalogue_icons() if icons is None else icons)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        got = list(pool.map(lambda pair: fetch(*pair, root=root), icons))

    return sum(got), len(got) - sum(got)
