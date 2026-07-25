# Combos, talents, evolution costs, item names, and cannon recipes decoded from the
# same BCData tarball the catalogue and stats already come from - one tarball pass.

import io
import json
import tarfile
from datetime import date
from functools import cache
from itertools import count
from pathlib import Path

from neko.bcdata import METADATA_URL, _get, _member, latest_version, release_url
from neko.region import DEFAULT_REGION, data_path, spec

COMBOS_FILE = "combos.json"
TALENTS_FILE = "talents.json"
EVOLVE_FILE = "evolve.json"
ITEMS_FILE = "items.json"
CANNON_FILE = "cannon.json"

# The record collection each document is counted by when it's rewritten.
_COUNTED = {
    COMBOS_FILE: "combos",
    TALENTS_FILE: "units",
    EVOLVE_FILE: "units",
    ITEMS_FILE: "items",
    CANNON_FILE: "cannons",
}

COMBO_SIZES = ("Sm", "M", "L", "XL")

# SkillAcquisition.csv holds 8 talent slots per unit, 14 columns each after (ID, typeID);
# slots flagged limit=1 are Ultra Talents (they trail the normal ones).
_SLOT_FIELDS = 14
_SLOTS = 8

# NyancomboData.csv: id, two unlock fields, five (unit, form) pairs, effect, size, -1.
_COMBO_PAIRS = slice(3, 13)
_COMBO_EFFECT = 13
_COMBO_SIZE = 14

# unitbuy.csv evolution block: True Form at (level c25, XP c27, item pairs c28-37),
# Ultra Form at (level c26, XP c38, item pairs c39-48); level -1 means no such form.
_TF_LEVEL, _UF_LEVEL, _TF_XP, _UF_XP = 25, 26, 27, 38
_TF_ITEMS = slice(28, 38)
_UF_ITEMS = slice(39, 49)

# Castle recipe rows: build time (hours), engineers, then eight material counts -
# regular materials in c2-9 (CastleRecipe files, order CANNON_MATERIALS) or their Z
# versions in c10-17 (Base/Deco files, order CANNON_Z_MATERIALS). The first two
# CastleRecipe rows are the one-time construction stages; the rest are Lv1+ upgrades.
_RECIPE_REGULAR = slice(2, 10)
_RECIPE_Z = slice(10, 18)
_CONSTRUCTION_ROWS = 2
CANNON_MATERIALS = (85, 86, 87, 88, 89, 90, 91, 140)
CANNON_Z_MATERIALS = (187, 188, 189, 190, 191, 192, 193, 194)

_EMPTY_FIELD = "＠"


def _ints(line: str) -> list[int]:
    """The line's comma cells as integers, junk as zero."""
    return [int(c) if c.strip().lstrip("-").isdigit() else 0 for c in line.split(",")]


def parse_combos(
    data_text: str,
    names_text: str,
    effects_text: str,
    params_text: str,
    filters_text: str,
    region: str = DEFAULT_REGION,
) -> dict:
    """The combo document: named combos with their units, effect, size, the per-size
    effect magnitudes table, and the game's own filter groupings of effect types."""
    separator = spec(region).separator
    names = [line.split(separator)[0].strip() for line in names_text.splitlines()]
    effects = [line.split(separator)[0].strip() for line in effects_text.splitlines()]
    values = [
        [int(c) for c in line.split("\t")[: len(COMBO_SIZES)]]
        for line in params_text.splitlines()
        if line.strip()
    ]
    # NyancomboFilter.tsv: a show-everything first line, then one effect group per line.
    categories = [
        [int(c) for c in line.split("\t") if c.strip()]
        for line in filters_text.splitlines()[1:]
        if line.strip()
    ]

    combos = []
    for line in data_text.splitlines():
        if not line[:1].isdigit():
            continue
        cells = _ints(line)
        combo_id = cells[0]
        name = names[combo_id] if combo_id < len(names) else ""
        if not name or name == _EMPTY_FIELD:
            continue
        pairs = cells[_COMBO_PAIRS]
        units = [[pairs[i], pairs[i + 1]] for i in range(0, len(pairs), 2) if pairs[i] >= 0]
        combos.append(
            {
                "id": combo_id,
                "name": name,
                "effect": cells[_COMBO_EFFECT],
                "size": cells[_COMBO_SIZE],
                "units": units,
            }
        )

    return {
        "sizes": list(COMBO_SIZES),
        "effects": effects,
        "values": values,
        "categories": categories,
        "combos": combos,
    }


def parse_talents(
    acquisition_text: str, levels_text: str, descriptions_text: str, region: str = DEFAULT_REGION
) -> dict:
    """The talent document: per-unit slots (Ultra Talents flagged), NP cost curves,
    and the description texts the slots reference."""
    units: dict[int, list[dict]] = {}
    for line in acquisition_text.splitlines()[1:]:
        cells = _ints(line)
        slots = []
        for start in range(2, 2 + _SLOTS * _SLOT_FIELDS, _SLOT_FIELDS):
            slot = cells[start : start + _SLOT_FIELDS]
            if len(slot) < _SLOT_FIELDS or not slot[0]:
                continue
            params = [slot[2 + i : 4 + i] for i in range(0, 8, 2)]
            slots.append(
                {
                    "ability": slot[0],
                    "max": max(slot[1], 1),
                    "params": [p for p in params if any(p)],
                    "text": slot[10],
                    "curve": slot[11],
                    "ultra": slot[13] == 1,
                }
            )
        if slots:
            units[cells[0]] = slots

    curves = {}
    for line in levels_text.splitlines()[1:]:
        cells = [c for c in line.split(",") if c.strip()]
        if cells:
            curves[int(cells[0])] = [int(c) for c in cells[1:]]

    texts = {}
    for line in descriptions_text.splitlines()[1:]:
        text_id, _, text = line.partition(spec(region).separator)
        if text_id.strip().isdigit():
            texts[int(text_id)] = text.strip()

    return {"units": units, "curves": curves, "texts": texts}


def _form_cost(level: int, xp: int, pairs: list[int]) -> dict | None:
    """One form's evolution cost, or None when the form doesn't exist (level -1)."""
    if level < 0:
        return None
    items = [[pairs[i], pairs[i + 1]] for i in range(0, len(pairs), 2) if pairs[i]]
    return {"level": level, "xp": xp, "items": items}


def parse_evolve(unitbuy_text: str) -> dict[int, dict]:
    """Per-unit True/Ultra Form evolution costs from unitbuy.csv; only units where
    some cost exists (XP or items) are kept."""
    evolves = {}
    for unit_id, line in enumerate(unitbuy_text.splitlines()):
        cells = _ints(line)
        if len(cells) <= _UF_ITEMS.stop - 1:
            cells += [0] * (_UF_ITEMS.stop - len(cells))
        tf = _form_cost(cells[_TF_LEVEL], cells[_TF_XP], cells[_TF_ITEMS])
        uf = _form_cost(cells[_UF_LEVEL], cells[_UF_XP], cells[_UF_ITEMS])
        if (tf and (tf["xp"] or tf["items"])) or (uf and (uf["xp"] or uf["items"])):
            evolves[unit_id] = {"tf": tf, "uf": uf}

    return evolves


def parse_items(names_text: str, region: str = DEFAULT_REGION) -> dict[int, str]:
    """Item id (its GatyaitemName row) to display name; blank and dummy rows dropped."""
    separator = spec(region).separator

    items = {}
    for item_id, line in enumerate(names_text.splitlines()):
        name = line.split(separator)[0].strip()
        if name and name != "dummy" and name != _EMPTY_FIELD:
            items[item_id] = name

    return items


def _recipe_rows(text: str, counts: slice) -> list[list[int]]:
    """[time, engineers, eight material counts] per castle recipe line."""
    return [_ints(line)[:2] + _ints(line)[counts] for line in text.splitlines() if line.strip()]


def parse_cannons(
    descriptions_text: str,
    recipes: dict[int, dict[str, str | None]],
    region: str = DEFAULT_REGION,
) -> list[dict]:
    """Per-cannon development recipes: the cannon part's construction stages and
    level costs, plus the foundation/style parts' Z-material level costs."""
    separator = spec(region).separator

    names = {}
    for line in descriptions_text.splitlines():
        cells = line.split(separator)
        if cells[0].strip().isdigit():
            names[int(cells[0])] = cells[1].strip()

    cannons = []
    for cannon_id, texts in sorted(recipes.items()):
        rows = _recipe_rows(texts["cannon"], _RECIPE_REGULAR)
        parts = {
            "cannon": {
                "construction": rows[:_CONSTRUCTION_ROWS],
                "levels": rows[_CONSTRUCTION_ROWS:],
            }
        }
        for key in ("base", "deco"):
            if texts.get(key):
                parts[key] = {"construction": [], "levels": _recipe_rows(texts[key], _RECIPE_Z)}
        cannons.append(
            {"id": cannon_id, "name": names.get(cannon_id, f"Cannon {cannon_id}"), "parts": parts}
        )

    return cannons


def build_gamedata(tarball: bytes, region: str = DEFAULT_REGION) -> dict[str, dict]:
    """All five documents from one tarball pass, keyed by their file name."""
    locale = spec(region).locale
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:xz") as tar:
        combos = parse_combos(
            _member(tar, "DataLocal/NyancomboData.csv"),
            _member(tar, f"resLocal/Nyancombo_{locale}.csv"),
            _member(tar, f"resLocal/Nyancombo1_{locale}.csv"),
            _member(tar, "DataLocal/NyancomboParam.tsv"),
            _member(tar, "DataLocal/NyancomboFilter.tsv"),
            region,
        )
        talents = parse_talents(
            _member(tar, "DataLocal/SkillAcquisition.csv"),
            _member(tar, "DataLocal/SkillLevel.csv"),
            _member(tar, "resLocal/SkillDescriptions.csv"),
            region,
        )
        evolve = {"units": parse_evolve(_member(tar, "DataLocal/unitbuy.csv"))}
        items = {"items": parse_items(_member(tar, "resLocal/GatyaitemName.csv"), region)}
        recipes = {}
        for index in count():
            cannon_text = _member(tar, f"DataLocal/CastleRecipe_{index:03d}.csv", optional=True)
            if cannon_text is None:
                break
            recipes[index] = {
                "cannon": cannon_text,
                "base": _member(tar, f"DataLocal/BaseRecipe_{index:03d}.csv", optional=True),
                "deco": _member(tar, f"DataLocal/DecoRecipe_{index:03d}.csv", optional=True),
            }
        cannon = {
            "materials": list(CANNON_MATERIALS),
            "zmaterials": list(CANNON_Z_MATERIALS),
            "cannons": parse_cannons(
                _member(tar, "resLocal/CastleRecipeDescriptions.csv"), recipes, region
            ),
        }

    stamp = {"fetched": date.today().isoformat()}
    return {
        COMBOS_FILE: stamp | combos,
        TALENTS_FILE: stamp | talents,
        EVOLVE_FILE: stamp | evolve,
        ITEMS_FILE: stamp | items,
        CANNON_FILE: stamp | cannon,
    }


def refresh(tarball: bytes | None = None, region: str = DEFAULT_REGION) -> dict[str, int]:
    """Rebuild one region's five gamedata JSONs from the live mirror (or a pre-downloaded
    tarball); returns record counts per file name."""
    if tarball is None:
        metadata = json.loads(_get(METADATA_URL))
        tarball = _get(release_url(metadata, latest_version(metadata, region), region))

    documents = build_gamedata(tarball, region)
    counts = {}
    for name, document in documents.items():
        path = data_path(name, region)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        counts[name] = len(document[_COUNTED[name]])

    return counts


@cache
def _load(path: Path) -> dict:
    """A committed gamedata document; memoized like load_records - the files only
    change on a re-fetch (a fresh process) and every caller treats them read-only."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_combos(region: str | None = None) -> dict:
    """One region's committed combos document."""
    return _load(data_path(COMBOS_FILE, region))


def load_talents(region: str | None = None) -> dict:
    """One region's committed talents document."""
    return _load(data_path(TALENTS_FILE, region))


def load_evolve(region: str | None = None) -> dict:
    """One region's committed evolution-costs document."""
    return _load(data_path(EVOLVE_FILE, region))


def load_items(region: str | None = None) -> dict:
    """One region's committed item-names document."""
    return _load(data_path(ITEMS_FILE, region))


def load_cannons(region: str | None = None) -> dict:
    """One region's committed cannon-recipes document."""
    return _load(data_path(CANNON_FILE, region))
