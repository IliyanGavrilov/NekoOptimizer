import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from neko.models import Rarity

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
    """A catalogue unit: canonical PONOS id, its form names (base first), and rarity."""

    unit_id: int
    forms: tuple[str, ...]
    rarity: Rarity

    @property
    def name(self) -> str:
        """The base-form name - what godfat's rolls label this unit by."""
        return self.forms[0] if self.forms else ""


def parse_forms(text: str) -> tuple[str, ...]:
    """Form names from one Unit_Explanation file (one per line, name in pipe-field 0)."""
    forms = []
    for line in text.splitlines():
        name = line.split("|", 1)[0].strip()
        if name:
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
    rarities: Mapping[int, Rarity], forms: Mapping[int, tuple[str, ...]]
) -> dict[int, Unit]:
    """Join rarities and form-names into {unit_id: Unit}; a unit needs both."""
    catalogue: dict[int, Unit] = {}
    for unit_id, names in forms.items():
        rarity = rarities.get(unit_id)
        if rarity is not None and names:
            catalogue[unit_id] = Unit(unit_id, tuple(names), rarity)
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
