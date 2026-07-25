# Uber rankings come from The Battle Cats Tier List's cumulative page: community
# shorthand names, resolved onto catalogue unit ids by name matching.

import html
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from neko.bcdata import _get, load_records
from neko.gachadata import load_pools
from neko.models import Rarity

SITE = "https://www.battlecatstierlist.com"
TIER_LIST_URL = f"{SITE}/current-tier-list"
TIERS_PATH = Path(__file__).parent / "data" / "tiers.json"

# Which catalogue units a list's names may resolve to. Most lists rank the standard
# capsule pool; a collab's ranks that collab's ubers, whose "<name> Cat" rare and
# "Li'l <name>" special would otherwise tie with them on a bare first name; the non-uber
# lists rank exactly what the capsule filter drops, so they take the whole catalogue.
CAPSULE, UBERS, EVERYTHING = "capsule", "ubers", "everything"
_SCOPES = {"collab-tier-lists": UBERS, "non-uber-tier-lists": EVERYTHING}
# The Legend Rares list spans every legend, collab ones included, so the capsule filter
# its category would otherwise get drops the very units it ranks.
_PATH_SCOPES = {"/tier-lists/miscellaneous-tier-lists/legend-rares": UBERS}
_UBER_RARITIES = frozenset({Rarity.UBER_SUPER_RARE.value, Rarity.LEGEND_RARE.value})

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
    # Per-set lists name a unit by its bare first name, which ties with its own seasonal
    # or non-uber namesake; the set's own list always means the original.
    "keiji": 72,  # Maeda Keiji, not Keiji Claus
    "yukimura": 71,  # Sanada Yukimura, not Count Yukimura
    "mekako": 195,  # Mekako Saionji, not Sweet Love Mekako
    "chronos": 439,  # Empress Chronos, not Chronos the Bride
    "satoru": 617,  # Summoner Satoru, not Rabbit Satoru
    "nurse": 143,  # Nurse Cat, not Yuletide Nurse
    "hermit": 352,  # Hermit Cat, not HUGE HERMIT
    "shaman": 52,  # Shaman Cat, not Shaman Khan
    "sumo": 21,  # Sumo Cat, not Mummy Sumo
    "ninja": 18,  # Ninja Cat, not Mr. Ninja
    "valkyrie": 24,  # Valkyrie Cat, not Li'l Valkyrie
    "cow": 4,  # Cow Cat, not Cow Princess
    "ushi": 451,  # Ushiwakamaru
    "idi": 568,  # Idi:N
    # Collab guests the site prefixes or spells out to keep them apart from namesakes.
    "sf balrog": 572,  # Balrog, the Street Fighter one
    "sf sakura": 680,  # Sakura
    "sf vega": 573,  # Vega
    "e.honda": 571,  # E. Honda
    "m.bison": 575,  # M. Bison
    "sonic the hedgehog": 803,  # Sonic
    "shadow the hedgehog": 806,  # Shadow
}

_NOISE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.IGNORECASE)
_BLOCK = re.compile(r"</?(?:p|div|br|li|tr|td|th|h[1-6]|section|article)\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
# The cumulative list writes "SS: a, b"; the per-set pages write "SS - a, b".
_ROW = re.compile(
    rf"^({'|'.join(re.escape(t) for t in sorted(TIER_ORDER, key=len, reverse=True))})"
    r"(?::| -) (.+)$"
)
_ENTRY = re.compile(r"(.+?)(?: \((UF|UT|T)\))?")  # T is the non-uber lists' True Form
_EMPTY = frozenset({"n/a", "none", "-"})  # how an empty tier is spelled
_NAV_LINK = re.compile(
    r'href="/tier-lists/([a-z0-9-]+)/([a-z0-9-]+)"[^>]*data-level="3"[^>]*>([^<]+)</a>'
)


def _normalize(name: str) -> str:
    """Lowercased, ASCII apostrophes, hyphens as spaces - the key both sides match on."""
    return " ".join(name.lower().replace("’", "'").replace("-", " ").split())


def _text(page: str) -> str:
    """The page's visible text, one line per block. Only block tags break the line: the
    site styles parts of a word with its own span, and breaking there splits names."""
    body = _BLOCK.sub("\n", _NOISE.sub("", page))

    return html.unescape(_TAGS.sub("", body))


def parse_tiers(page: str) -> list[tuple[str, str, str | None]]:
    """The page's Text Version as (tier, community name, UF/UT boost) rows, in order."""
    rows: list[tuple[str, str, str | None]] = []
    for line in _text(page).splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            continue

        tier, body = match.groups()
        for item in body.split(","):
            entry = _ENTRY.fullmatch(item.strip())
            if entry is not None and entry.group(1).lower() not in _EMPTY:
                rows.append((tier, entry.group(1), entry.group(2)))

    return rows


@dataclass(frozen=True, slots=True)
class TierListPage:
    """One per-set tier list the site's nav links to, and the catalogue scope its names
    resolve against."""

    path: str
    label: str
    category: str
    scope: str


def _category_label(slug: str) -> str:
    """A nav section's path segment as its display label: "non-uber-tier-lists" -> "Non-Uber"."""
    return "-".join(word.capitalize() for word in slug.removesuffix("-tier-lists").split("-"))


def discover_lists(page: str) -> list[TierListPage]:
    """Every per-set tier list linked from the site nav, in nav order. Any page carries
    the whole nav, and renders it several times over, so the first sighting wins."""
    found: dict[str, TierListPage] = {}
    for category, name, label in _NAV_LINK.findall(page):
        path = f"/tier-lists/{category}/{name}"
        found.setdefault(
            path,
            TierListPage(
                path,
                html.unescape(label).strip(),
                _category_label(category),
                _PATH_SCOPES.get(path, _SCOPES.get(category, CAPSULE)),
            ),
        )

    return list(found.values())


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
    subset of "Winter General Kaihime"), where the shortest label wins - a bare "Axe" is
    the plain Axe Cat, not the Crazed / Li'l / Brainwashed one, each of which the site
    ranks on its own list under its own prefixed name. Longer names resolve first and
    claim their unit, so a bare "Keiji" falls to the base unit once "Keiji Claus" took
    the variant.

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
            sizes: dict[int, int] = {}
            for label, unit_ids in index.items():
                words = label.split()
                if tokens <= set(words):
                    for unit_id in unit_ids - claimed:
                        sizes[unit_id] = min(len(words), sizes.get(unit_id, len(words)))

            shortest = min(sizes.values(), default=0)
            ids = {unit_id for unit_id, size in sizes.items() if size == shortest}
        if len(ids) == 1:
            unit_id = ids.pop()
            resolved[name] = unit_id
            claimed.add(unit_id)

    return resolved


def tier_records(
    rows: Iterable[tuple[str, str, str | None]],
    resolution: Mapping[str, int],
    records: Iterable[Mapping],
    source: str = TIER_LIST_URL,
) -> dict:
    """The parsed rows as a tiers.json document: entries keep the list's order and
    carry the catalogue's canonical unit name once resolved."""
    names = {record["id"]: record["name"] for record in records}
    tiers: dict[str, list[dict]] = {}
    for tier, name, boost in rows:
        unit_id = resolution.get(name)
        tiers.setdefault(tier, []).append(
            {"name": names.get(unit_id, name), "unit_id": unit_id, "boost": boost}
        )

    return {
        "source": source,
        "fetched": date.today().isoformat(),
        "tiers": [{"tier": tier, "entries": tiers[tier]} for tier in TIER_ORDER if tier in tiers],
    }


def load_tiers(path: Path = TIERS_PATH) -> dict:
    """The committed tier-list document."""
    return json.loads(path.read_text(encoding="utf-8"))


def _document(
    rows: list[tuple[str, str, str | None]],
    records: Iterable[Mapping],
    eligible: set[int] | None,
    source: str,
) -> tuple[dict, set[str]]:
    """One list's document plus the community names it couldn't place."""
    resolution = resolve_names((name for _, name, _ in rows), records, eligible)

    return (
        tier_records(rows, resolution, records, source),
        {name for _, name, _ in rows if name not in resolution},
    )


def refresh() -> tuple[int, int, list[str]]:
    """Fetch the cumulative tier list plus every per-set list its nav links to, and
    rewrite tiers.json (network); returns the entry count, the per-set list count, and
    the community names that didn't resolve."""
    page = _get(TIER_LIST_URL).decode("utf-8", "replace")
    records = load_records()
    eligible = eligible_units(records, load_pools())
    scopes = {
        CAPSULE: eligible,
        UBERS: {r["id"] for r in records if r["rarity"] in _UBER_RARITIES},
        EVERYTHING: None,
    }

    rows = parse_tiers(page)
    doc, unmatched = _document(rows, records, eligible, TIER_LIST_URL)
    total = len(rows)

    lists = []
    for entry in discover_lists(page):
        url = SITE + entry.path
        entry_rows = parse_tiers(_get(url).decode("utf-8", "replace"))
        listed, missing = _document(entry_rows, records, scopes[entry.scope], url)
        lists.append(
            {**listed, "path": entry.path, "label": entry.label, "category": entry.category}
        )
        total += len(entry_rows)
        unmatched |= missing

    doc["lists"] = lists
    TIERS_PATH.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    return total, len(lists), sorted(unmatched)
