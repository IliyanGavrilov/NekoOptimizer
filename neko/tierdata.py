# Uber rankings come from The Battle Cats Tier List's cumulative page: community
# shorthand names, resolved onto catalogue unit ids by name matching.

import html
import json
import re
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path

from neko.bcdata import _get, load_records
from neko.gachadata import load_pools

TIER_LIST_URL = "https://www.battlecatstierlist.com/current-tier-list"
TIERS_PATH = Path(__file__).parent / "data" / "tiers.json"

# Every tier the cumulative list uses, best first.
TIER_ORDER = (
    "SSS", "SS", "S+", "S", "S-",
    "A+", "A", "A-", "B+", "B", "B-",
    "C+", "C", "C-", "D+", "D", "D-",
    "E+", "E", "E-", "F+", "F", "F-",
)  # fmt: skip

# Community names whose official counterparts share no usable tokens (the epicfest
# "Dark" twins, nicknames) or that stay ambiguous even after longer names claim theirs.
_ALIASES = {
    "dark lunos": 859,  # Lone Moon Lunos
    "dark luna": 787,  # Netherworld Nymph Lunacia
    "dark phono": 705,  # King of Doom Phono
    "dark kasli": 543,  # Kasli the Bane
    "saki": 393,  # Saki Nijima, not the Sharpshooter/Squirtgun seasonals
    "kenshin": 158,  # Uesugi Kenshin, not the collab Kenshins
    "aphrodite": 259,  # Radiant Aphrodite
    "hanzo": 649,  # Hattori Hanzo
    "zeus": 257,  # Thunder God Zeus
    "tomoe": 725,  # Ninja Girl Tomoe, not the collab Mami Tomoe
    "musashi": 448,  # Musashi Miyamoto, the Legend Rare
    "empress": 612,  # Princess Cat, the Legend Rare (evolves into Empress Cat)
    "emperor": 586,  # Emperor Cat, the Legend Rare
    "morta launcher": 799,  # Mighty Morta-Loncha
    "bikiniluga": 564,  # Summerluga
    "li'l valk": 435,  # Li'l Valkyrie
    "li'l valk dark": 484,  # Li'l Valkyrie Dark
    "bride balaluga": 711,  # Betrothed Balaluga
}

_TAGS = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>")
_ROW = re.compile(
    rf"^({'|'.join(re.escape(t) for t in sorted(TIER_ORDER, key=len, reverse=True))}): (.+)$"
)
_ENTRY = re.compile(r"(.+?)(?: \((UF|UT)\))?")


def _normalize(name: str) -> str:
    """Lowercased, ASCII apostrophes, hyphens as spaces - the key both sides match on."""
    return " ".join(name.lower().replace("’", "'").replace("-", " ").split())


def parse_tiers(page: str) -> list[tuple[str, str, str | None]]:
    """The page's Text Version as (tier, community name, UF/UT boost) rows, in order."""
    rows: list[tuple[str, str, str | None]] = []
    for line in html.unescape(_TAGS.sub("\n", page)).splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            continue

        tier, body = match.groups()
        for item in body.split(","):
            entry = _ENTRY.fullmatch(item.strip())
            if entry is not None:
                rows.append((tier, entry.group(1), entry.group(2)))

    return rows


def eligible_units(records: Iterable[Mapping], pools: Mapping[int, Iterable[int]]) -> set[int]:
    """The unit ids the tier list can rank: the standard permanent-capsule pool only,
    never collab or one-off event guests. A unit qualifies if the Cat Guide gives it a
    gacha set, or it shares a gacha pool with such a unit - fest columns bundle set-less
    exclusives and legends alongside their sets, so those come along. Collab banners carry
    only set-less guests (their picture-book source is the event, not a capsule), so
    nothing in a pure-collab pool ever qualifies."""
    setted = {record["id"] for record in records if record.get("set")}
    eligible = set(setted)
    for members in pools.values():
        if any(unit_id in setted for unit_id in members):
            eligible.update(members)

    return eligible


def resolve_names(
    names: Iterable[str], records: Iterable[Mapping], eligible: set[int] | None = None
) -> dict[str, int]:
    """Match community names onto catalogue unit ids: an exact name/form match first,
    then the alias table, then an unclaimed token-subset match ("Winter Kaihime" is a
    subset of "Winter General Kaihime"). Longer names resolve first and claim their
    unit, so a bare "Keiji" falls to the base unit once "Keiji Claus" took the variant.

    ``eligible`` (from eligible_units) limits the index to the standard capsule pool, so
    a name a collab unit shares - "Balrog" is a Street Fighter guest as well as the true
    form of the Dynamites' Lesser Demon Cat - resolves to the standard unit the list
    means."""
    index: dict[str, set[int]] = {}
    for record in records:
        if eligible is not None and record["id"] not in eligible:
            continue
        for label in (record["name"], *record["forms"]):
            if label:
                index.setdefault(_normalize(label), set()).add(record["id"])

    resolved: dict[str, int] = {}
    claimed: set[int] = set()
    for name in sorted(set(names), key=lambda n: (-len(_normalize(n)), n)):
        key = _normalize(name)
        ids = index.get(key, set()) - claimed
        if len(ids) != 1 and key in _ALIASES:
            ids = {_ALIASES[key]}
        if len(ids) != 1:
            tokens = set(key.split())
            ids = {
                unit_id
                for label, unit_ids in index.items()
                if tokens <= set(label.split())
                for unit_id in unit_ids
            } - claimed
        if len(ids) == 1:
            unit_id = ids.pop()
            resolved[name] = unit_id
            claimed.add(unit_id)

    return resolved


def tier_records(
    rows: Iterable[tuple[str, str, str | None]],
    resolution: Mapping[str, int],
    records: Iterable[Mapping],
) -> dict:
    """The parsed rows as the tiers.json document: entries keep the list's order and
    carry the catalogue's canonical unit name once resolved."""
    names = {record["id"]: record["name"] for record in records}
    tiers: dict[str, list[dict]] = {}
    for tier, name, boost in rows:
        unit_id = resolution.get(name)
        tiers.setdefault(tier, []).append(
            {"name": names.get(unit_id, name), "unit_id": unit_id, "boost": boost}
        )

    return {
        "source": TIER_LIST_URL,
        "fetched": date.today().isoformat(),
        "tiers": [{"tier": tier, "entries": tiers[tier]} for tier in TIER_ORDER if tier in tiers],
    }


def load_tiers(path: Path = TIERS_PATH) -> dict:
    """The committed tier-list document."""
    return json.loads(path.read_text(encoding="utf-8"))


def refresh() -> tuple[int, list[str]]:
    """Fetch the live tier list and rewrite tiers.json (network); returns the entry
    count and the community names that didn't resolve."""
    rows = parse_tiers(_get(TIER_LIST_URL).decode("utf-8", "replace"))
    records = load_records()
    eligible = eligible_units(records, load_pools())
    resolution = resolve_names((name for _, name, _ in rows), records, eligible)
    TIERS_PATH.write_text(
        json.dumps(tier_records(rows, resolution, records), ensure_ascii=False),
        encoding="utf-8",
    )

    return len(rows), sorted({name for _, name, _ in rows if name not in resolution})
