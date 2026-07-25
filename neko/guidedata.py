# The in-game Cat Guide arrangement per region, from the wiki's bot-maintained
# Cat_Guide/Units page: rarity sections sub-grouped by unlock source, an order the
# game data itself never states. Names are resolved onto catalogue unit ids.

import json
import re
from collections.abc import Iterable, Mapping
from datetime import date
from functools import cache
from pathlib import Path

from neko.bcdata import _get, load_records
from neko.region import DEFAULT_REGION
from neko.tierdata import _normalize

GUIDE_API = (
    "https://battlecats.miraheze.org/w/api.php"
    "?action=parse&page=Cat_Guide/Units&prop=wikitext&format=json&formatversion=2"
)
GUIDE_PATH = Path(__file__).parent / "data" / "guide_order.json"

# The page's tabber labels onto our region codes.
_REGIONS = {
    "English Version": "en",
    "Japanese Version": "jp",
    "Korean Version": "kr",
    "Taiwanese Version": "tw",
}

_CATGUIDE = re.compile(r"\{\{CatGuide\|(.*?)\}\}", re.S)
_TAB_LABEL = re.compile(r"([A-Za-z]+ Version)=")

# Wiki spellings whose catalogue counterparts differ beyond normalization: the page
# suffixes the two same-named Cat Bros units with their rarity, and respells Newton.
_ALIASES = {
    "cat bros ex": 108,
    "cat bros r": 501,
    "master of logic newtone": 801,
}


def _key(name: str) -> str:
    """The match key: tierdata's normalization plus a fullwidth-ampersand fold (the
    catalogue spells collab duos with ＆, the wiki with &)."""
    return _normalize(name.replace("＆", "&"))


def parse_guide(wikitext: str) -> dict[str, list[str]]:
    """Region code to its ordered unit names from the page's tabber sections."""
    labels = [(match.start(), match.group(1)) for match in _TAB_LABEL.finditer(wikitext)]
    bounds = [start for start, _ in labels[1:]] + [len(wikitext)]

    regions = {}
    for (start, label), end in zip(labels, bounds, strict=True):
        region = _REGIONS.get(label)
        match = _CATGUIDE.search(wikitext, start, end)
        if region and match:
            regions[region] = [name.strip() for name in match.group(1).split("|") if name.strip()]

    return regions


def resolve_names(
    names: Iterable[str], records: Iterable[Mapping] | None = None
) -> tuple[list[int], list[str]]:
    """The names as ordered catalogue unit ids, plus the names that didn't resolve
    (region-exclusive units the catalogue doesn't carry)."""
    records = load_records() if records is None else records
    by_name = {_key(record["name"]): record["id"] for record in records}

    ids, unmatched = [], []
    for name in names:
        unit_id = _ALIASES.get(_key(name), by_name.get(_key(name)))
        if unit_id is None:
            unmatched.append(name)
        elif unit_id not in ids:
            ids.append(unit_id)

    return ids, unmatched


def refresh() -> dict[str, tuple[int, list[str]]]:
    """Rebuild guide_order.json from the wiki; returns each region's resolved count
    and the names that didn't match (for alias curation). Every tab of the page names
    its units in English - only the ORDER is per region - so they all resolve against
    the English catalogue, and the unit ids that come out are version-independent."""
    wikitext = json.loads(_get(GUIDE_API))["parse"]["wikitext"]
    regions = parse_guide(wikitext)
    records = load_records(DEFAULT_REGION)

    resolved, report = {}, {}
    for region, names in sorted(regions.items()):
        ids, unmatched = resolve_names(names, records)
        resolved[region] = ids
        report[region] = (len(ids), unmatched)

    document = {"source": GUIDE_API, "fetched": date.today().isoformat(), "regions": resolved}
    GUIDE_PATH.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    return report


@cache
def load_guide(path: Path = GUIDE_PATH) -> dict:
    """The committed guide-order document. Memoized: the file only changes on a
    re-fetch (a fresh process), and every caller treats it read-only."""
    return json.loads(path.read_text(encoding="utf-8"))
