# battlecatsinfo's MIT-licensed unit tables, extracted from each game version within days
# of its release - BCData can lag a version behind, so these fill in the units and forms
# it hasn't caught up on yet. Both files hold one row per unit id after a header row.

import csv
import io
from collections.abc import Mapping
from dataclasses import replace

from neko.bcdata import _get
from neko.catalogue import RARITY_BY_CODE, Unit, form_names

_DATA = "https://raw.githubusercontent.com/battlecatsinfo/battlecatsinfo.github.io/master/data"


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))


def parse_units(cat_text: str, names_text: str, region: str) -> dict[int, Unit]:
    """Every unit named in the version's language: rarity from cat.tsv, forms from tcat.tsv
    (a column per version). A unit the version hasn't released has no name there."""
    units = {}
    for unit_id, (row, names) in enumerate(zip(_rows(cat_text), _rows(names_text), strict=True)):
        forms = form_names(names[region].split("|"))
        rarity = RARITY_BY_CODE.get(int(row["rarity"]))
        if forms and rarity is not None:
            units[unit_id] = Unit(unit_id, forms, rarity)

    return units


# cat.tsv's evolution columns, and the form each one evolves a unit into.
_EVOLUTIONS = (("tf", "evol_require", 3), ("uf", "evol4_require", 4))


def _form_cost(cell: str) -> dict:
    """One evolution's cost from a 'count!item|...' cell, where item 0 is XP. The level
    it unlocks at isn't in the table."""
    xp, items = 0, []
    for pair in cell.split("|"):
        amount, item_id = map(int, pair.split("!"))
        if item_id:
            items.append([item_id, amount])
        else:
            xp += amount

    return {"level": None, "xp": xp, "items": items}


def parse_evolve(cat_text: str, names_text: str, region: str) -> dict[int, dict]:
    """True/Ultra Form costs for the forms the version has. cat.tsv holds one set of costs
    for every version, so a form only counts once the version's own names include it -
    an evolution one version got first stays out of the others."""
    evolves = {}
    for unit_id, (row, names) in enumerate(zip(_rows(cat_text), _rows(names_text), strict=True)):
        named = len(form_names(names[region].split("|")))
        forms = {
            key: _form_cost(row[column]) if row[column] and named >= nth else None
            for key, column, nth in _EVOLUTIONS
        }
        if any(forms.values()):
            evolves[unit_id] = forms

    return evolves


def fill_forms(catalogue: Mapping[int, Unit], newer: Mapping[int, Unit]) -> dict[int, Unit]:
    """The catalogue with the units it lacks added and the forms it lacks appended;
    the catalogue's own names win wherever it has them."""
    filled = {**newer, **catalogue}
    for unit_id, unit in catalogue.items():
        later = newer.get(unit_id)
        if later and len(later.forms) > len(unit.forms):
            filled[unit_id] = replace(unit, forms=unit.forms + later.forms[len(unit.forms) :])

    return filled


def fill_evolve(evolves: Mapping[int, dict], newer: Mapping[int, dict]) -> dict[int, dict]:
    """The evolution costs with the forms they lack filled in from battlecatsinfo; a form
    the costs already have keeps its own."""
    filled = dict(evolves)
    for unit_id, forms in newer.items():
        own = filled.get(unit_id, {"tf": None, "uf": None})
        filled[unit_id] = {key: own.get(key) or forms[key] for key in ("tf", "uf")}

    return filled


def _download() -> tuple[str, str]:
    """cat.tsv and tcat.tsv as published now (network)."""
    return (
        _get(f"{_DATA}/cat.tsv").decode("utf-8"),
        _get(f"{_DATA}/tcat.tsv").decode("utf-8"),
    )


def download_units(region: str) -> dict[int, Unit]:
    """The live battlecatsinfo catalogue for one version (network)."""
    return parse_units(*_download(), region)


def download_evolve(region: str) -> dict[int, dict]:
    """The live battlecatsinfo evolution costs for one version (network)."""
    return parse_evolve(*_download(), region)
