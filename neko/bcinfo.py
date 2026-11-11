# battlecatsinfo's MIT-licensed unit tables, extracted from each game version within days
# of its release - BCData can lag a version behind, so these fill in the units it hasn't
# caught up on yet. Both files hold one row per unit id after a header row.

import csv
import io

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


def download_units(region: str) -> dict[int, Unit]:
    """The live battlecatsinfo catalogue for one version (network)."""
    cat = _get(f"{_DATA}/cat.tsv").decode("utf-8")
    names = _get(f"{_DATA}/tcat.tsv").decode("utf-8")

    return parse_units(cat, names, region)
