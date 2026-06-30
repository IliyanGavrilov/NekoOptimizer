import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import aiohttp

from neko.catalogue import Unit, build_catalogue, parse_forms, parse_rarities

# fieryhenry/BCData is archived, frozen at this version: our bootstrap catalogue source
# until a live pull (tbcml) replaces the fetch.
BCDATA_BASE = "https://raw.githubusercontent.com/fieryhenry/BCData/main/14.7.0en"

UNITS_PATH = Path(__file__).parent / "data" / "units.json"

Fetcher = Callable[[str], Awaitable[str]]


def unitbuy_url() -> str:
    return f"{BCDATA_BASE}/DataLocal/unitbuy.csv"


def names_url(unit_id: int) -> str:
    """The unit's name file - 1-based, so unit 0 lives in Unit_Explanation1_en.csv."""
    return f"{BCDATA_BASE}/resLocal/Unit_Explanation{unit_id + 1}_en.csv"


async def fetch_catalogue(fetch: Fetcher) -> dict[int, Unit]:
    """Fetch unitbuy plus every unit's name file and consolidate the catalogue. Units
    whose name file is missing (a 404 raises) are dropped."""
    rarities = parse_rarities(await fetch(unitbuy_url()))
    ids = sorted(rarities)
    texts = await asyncio.gather(
        *(fetch(names_url(unit_id)) for unit_id in ids), return_exceptions=True
    )
    forms = {
        unit_id: parse_forms(text)
        for unit_id, text in zip(ids, texts, strict=True)
        if isinstance(text, str)
    }
    return build_catalogue(rarities, forms)


def catalogue_records(catalogue: Mapping[int, Unit]) -> list[dict]:
    """The catalogue as id-sorted JSON records for units.json."""
    return [
        {
            "id": unit.unit_id,
            "name": unit.name,
            "rarity": unit.rarity.value,
            "forms": list(unit.forms),
        }
        for unit in sorted(catalogue.values(), key=lambda unit: unit.unit_id)
    ]


def make_fetcher(session: aiohttp.ClientSession, limit: int = 20) -> Fetcher:
    """A fetcher that caps concurrency, so the ~1000 name-file pulls stay polite."""
    semaphore = asyncio.Semaphore(limit)

    async def fetch(url: str) -> str:
        async with semaphore, session.get(url) as response:
            response.raise_for_status()
            return await response.text()

    return fetch


async def download_catalogue(limit: int = 20) -> dict[int, Unit]:
    """Fetch the catalogue straight from BCData over the network."""
    async with aiohttp.ClientSession() as session:
        return await fetch_catalogue(make_fetcher(session, limit))


def load_records(path: Path = UNITS_PATH) -> list[dict]:
    """The catalogue records previously written to units.json."""
    return json.loads(path.read_text(encoding="utf-8"))
