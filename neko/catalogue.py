import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from neko.models import Rarity
from neko.region import DEFAULT_REGION, spec

# Unit id = the row's 0-based index in unitbuy.csv (no header/id column); this column
# holds the rarity code.
_RARITY_COL = 13

# 0/1 (Normal/Special) are non-gacha units that never appear in a roll.
_RARITY_BY_CODE = {
    0: Rarity.NORMAL,
    1: Rarity.SPECIAL,
    2: Rarity.RARE,
    3: Rarity.SUPER_RARE,
    4: Rarity.UBER_SUPER_RARE,
    5: Rarity.LEGEND_RARE,
}


@dataclass(frozen=True, slots=True)
class Unit:
    """A catalogue unit: canonical PONOS id, its form names (base first), rarity, and the
    official gacha set it belongs to ('' for units outside a recurring capsule set)."""

    unit_id: int
    forms: tuple[str, ...]
    rarity: Rarity
    set_name: str = ""

    @property
    def name(self) -> str:
        """The base-form name - what godfat's rolls label this unit by."""
        return self.forms[0] if self.forms else ""


def parse_forms(text: str, region: str = DEFAULT_REGION) -> tuple[str, ...]:
    """Form names from one Unit_Explanation file (one per line, name in field 0).
    A line that repeats the previous name is an evolution the game hasn't released (or
    named) here yet - a placeholder row, not a real form - so it's dropped."""
    separator = spec(region).separator

    forms = []
    for line in text.splitlines():
        name = line.split(separator, 1)[0].strip()
        if name and (not forms or name != forms[-1]):
            forms.append(name)

    return tuple(forms)


def parse_rarities(unitbuy_text: str) -> dict[int, Rarity]:
    """Map each unit id (its unitbuy.csv row) to rarity; skip short or unknown rows."""
    rarities: dict[int, Rarity] = {}
    for unit_id, row in enumerate(csv.reader(unitbuy_text.splitlines())):
        if len(row) <= _RARITY_COL:
            continue

        try:
            code = int(row[_RARITY_COL])
        except ValueError:
            continue

        rarity = _RARITY_BY_CODE.get(code)
        if rarity is not None:
            rarities[unit_id] = rarity

    return rarities


# The Cat Guide names a unit's gacha set only for capsule units; for stage/collab units
# the same field holds a stage or event name instead, so it must be gated on the source -
# in the region's own words.
_CAPSULE_SOURCES = {
    "en": ("From Rare Capsule Event", "Collect from Limited Rare Capsules"),
    "jp": (
        "レアガチャイベント",
        "期間限定レアガチャイベント",
        "期間限定レアガチャイベントで入手可能",
    ),
    "tw": ("稀有轉蛋活動", "期間限定稀有轉蛋活動", "期間限定稀有轉蛋活動中可獲得"),
    "kr": (
        "레어 뽑기 이벤트",
        "기간 한정 레어 뽑기 이벤트",
        "기간 한정 레어 뽑기 이벤트로 획득 가능",
    ),
}
_EMPTY_FIELD = "＠"

# Outside English the set name arrives inside a sentence: 「The Dynamites」で入手可能.
_QUOTED = re.compile("「(.+?)」")


def parse_sets(picture_book_text: str, region: str = DEFAULT_REGION) -> dict[int, str]:
    """Map unit id (its nyankoPictureBook row) to its official gacha set name, e.g.
    'The Dynamites' - the name shown on the in-game banner image, which the event
    data's text field (a per-run marketing subtitle) never carries."""
    separator = spec(region).separator
    sources = _CAPSULE_SOURCES[region]

    sets: dict[int, str] = {}
    for unit_id, line in enumerate(picture_book_text.splitlines()):
        fields = line.split(separator)
        if len(fields) < 2 or fields[0].strip() not in sources:
            continue

        quoted = _QUOTED.search(fields[1])
        name = quoted.group(1).strip() if quoted else fields[1].strip()
        if name and name != _EMPTY_FIELD:
            sets[unit_id] = name

    return sets


def parse_pools(text: str) -> list[list[int]]:
    """Unit ids per GatyaDataSet pool row (each terminated by -1, trailing // dropped)."""
    pools: list[list[int]] = []
    for row in csv.reader(text.splitlines()):
        ids: list[int] = []
        for cell in row:
            try:
                value = int(cell.strip())
            except ValueError:
                break  # blank padding or the // comment: the pool has ended

            if value == -1:
                break

            ids.append(value)

        if ids:
            pools.append(ids)

    return pools


def build_catalogue(
    rarities: Mapping[int, Rarity],
    forms: Mapping[int, tuple[str, ...]],
    sets: Mapping[int, str] | None = None,
) -> dict[int, Unit]:
    """Join rarities, form-names and set names into {unit_id: Unit}; a unit needs the
    first two, set names are optional."""
    sets = sets or {}

    catalogue: dict[int, Unit] = {}
    for unit_id, names in forms.items():
        rarity = rarities.get(unit_id)
        if rarity is not None and names:
            catalogue[unit_id] = Unit(unit_id, tuple(names), rarity, sets.get(unit_id, ""))

    return catalogue


def name_index(units: Iterable) -> dict[str, int]:
    """Map base-form name -> unit id, for joining godfat's roll-names to the catalogue.
    Works on anything with .name/.unit_id (catalogue Units or DB rows)."""
    return {unit.name: unit.unit_id for unit in units}


def match_names(names: Iterable[str], index: Mapping[str, int]) -> tuple[dict[str, int], list[str]]:
    """Split roll-names into {name: unit_id} matches and the sorted names with no unit."""
    matches: dict[str, int] = {}
    unmatched: set[str] = set()

    for name in names:
        if name in index:
            matches[name] = index[name]
        else:
            unmatched.add(name)

    return matches, sorted(unmatched)
