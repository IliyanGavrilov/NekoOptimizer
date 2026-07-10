# Per-form combat stats decoded from the game's own unit CSVs (the BCData tarball the
# catalogue already comes from). The one number the tarball can't produce is the true
# attack frequency - it needs animation lengths shipped in a separate asset pack - so
# that column is joined in from battlecatsinfo's open data table.

import io
import json
import tarfile
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path

from neko.bcdata import METADATA_URL, _get, _member, latest_version, load_records, release_url

CATSTAT_URL = (
    "https://raw.githubusercontent.com/battlecatsinfo/battlecatsinfo.github.io"
    "/master/data/catstat.tsv"
)
STATS_PATH = Path(__file__).parent / "data" / "stats.json"

# Stats are quoted the way the wiki and every calculator quote them: level 30, with the
# Empire of Cats treasures maxed (a flat 2.5x on health and attack).
DISPLAY_LEVEL = 30

# A form's stat row can stop early (old units carry ~53 columns, current ones ~117);
# absent columns mean the ability didn't exist yet, so they pad as zeroes.
_COLUMNS = 117

# Column meanings follow the community map of unitNNN.csv (as encoded in fieryhenry's
# tbcml, the maintainer of the data mirror itself).
_TARGETS = (
    (10, "Red"),
    (16, "Floating"),
    (17, "Black"),
    (18, "Metal"),
    (20, "Angel"),
    (21, "Alien"),
    (22, "Zombie"),
    (78, "Relic"),
    (96, "Aku"),
    (19, "Traitless"),
    (54, "Witch"),
    (76, "Eva Angel"),
)

_IMMUNITIES = (
    (46, "Waves"),
    (48, "Knockback"),
    (49, "Freeze"),
    (50, "Slow"),
    (51, "Weaken"),
    (79, "Curse"),
    (90, "Toxic"),
    (91, "Surges"),
)

_FLAGS = (
    (23, "Strong"),
    (29, "Resistant"),
    (80, "Insanely tough"),
    (30, "Massive damage"),
    (81, "Insane damage"),
    (43, "Metal"),
    (32, "Attacks only targets"),
    (52, "Zombie Killer"),
    (53, "Witch Killer"),
    (77, "Eva Angel Killer"),
    (97, "Colossus Slayer"),
    (105, "Behemoth Slayer"),
    (111, "Sage Slayer"),
    (98, "Soul Strike"),
    (34, "Base Destroyer"),
    (33, "Extra money"),
    (47, "Wave Shield"),
    (109, "Counter-surge"),
)


def _secs(frames: int) -> str:
    return f"{frames / 30:.1f}s"


def parse_stat_rows(text: str) -> list[list[int]]:
    """One unit CSV as per-form integer rows, padded out to the full column set."""
    rows = []
    for line in text.splitlines():
        cells = [int(cell) if _is_int(cell) else 0 for cell in line.split(",")]
        if cells and any(cells):
            rows.append(cells + [0] * (_COLUMNS - len(cells)))

    return rows


def _is_int(cell: str) -> bool:
    cell = cell.strip()
    return cell.lstrip("-").isdigit()


def parse_curves(text: str) -> list[list[int]]:
    """unitlevel.csv as growth curves, one per unit id: the per-level stat gain (as a
    percentage of the level-1 base) for each ten-level block."""
    return [
        [int(cell) for cell in line.split(",") if cell.strip()]
        for line in text.splitlines()
        if line.strip()
    ]


def parse_frequencies(tsv: str) -> dict[tuple[int, int], int]:
    """{(unit id, form index): attack frequency in frames} from catstat.tsv, whose rows
    are one form each, grouped per unit in form order."""
    lines = tsv.splitlines()
    header = lines[0].split("\t")
    id_col, freq_col = header.index("id"), header.index("attack_frequency")

    seen: dict[int, int] = {}
    frequencies = {}
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) <= max(id_col, freq_col) or not _is_int(cells[id_col]):
            continue
        unit_id = int(cells[id_col])
        form = seen.get(unit_id, 0)
        seen[unit_id] = form + 1
        if _is_int(cells[freq_col]):
            frequencies[(unit_id, form)] = int(cells[freq_col])

    return frequencies


def growth_pct(curve: Iterable[int], level: int = DISPLAY_LEVEL) -> int:
    """A stat's size at a level as a percentage of its level-1 base (100 = unchanged)."""
    curve = list(curve)
    return 100 + sum(curve[(step - 2) // 10] for step in range(2, level + 1))


def _leveled(base: int, pct: int) -> int:
    # Level growth and the flat 2.5x treasure boost, floored once like the wiki quotes.
    return base * pct * 5 // 200


def _effects(row: list[int]) -> list[str]:
    """The form's abilities as short readable chips, in a stable notable-first order."""
    hits = [row[3]] + [hit for hit in (row[59], row[60]) if hit]
    out = []
    if len(hits) > 1:
        out.append(f"{len(hits)} hits ({' + '.join(f'{hit:,}' for hit in hits)})")
    out.extend(label for index, label in _FLAGS if row[index])
    if row[31]:
        out.append(f"Critical hit {row[31]}%")
    if row[82]:
        out.append(f"Savage blow {row[82]}% (+{row[83]}%)")
    if row[24]:
        out.append(f"Knockback {row[24]}%")
    if row[25]:
        out.append(f"Freeze {row[25]}% for {_secs(row[26])}")
    if row[27]:
        out.append(f"Slow {row[27]}% for {_secs(row[28])}")
    if row[37]:
        out.append(f"Weaken {row[37]}% to {row[39]}% for {_secs(row[38])}")
    if row[92]:
        out.append(f"Curse {row[92]}% for {_secs(row[93])}")
    if row[35]:
        kind = "Mini-wave" if row[94] else "Wave"
        out.append(f"{kind} {row[35]}% (Lv {row[36]})")
    if row[86]:
        # Surge coordinates are stored at 4x scale.
        lo, hi = sorted((row[87] // 4, (row[87] + row[88]) // 4))
        out.append(f"Surge {row[86]}% (Lv {row[89]}, {lo}~{hi})")
    if row[40]:
        out.append(f"Attack +{row[41]}% at {row[40]}% HP")
    if row[42]:
        out.append(f"Survives a lethal strike {row[42]}%")
    if row[70]:
        out.append(f"Breaks barriers {row[70]}%")
    if row[95]:
        out.append(f"Pierces shields {row[95]}%")
    if row[71]:
        out.append(f"Warp {row[71]}%")
    if row[84]:
        out.append(f"Dodge {row[84]}% for {_secs(row[85])}")
    if row[44] or row[45]:
        lo, hi = sorted((row[44], row[44] + row[45]))
        kind = "Omni strike" if row[45] < 0 else "Long distance"
        out.append(f"{kind} {lo}~{hi}")

    return out


def form_record(row: list[int], curve: Iterable[int], frequency: int | None) -> dict:
    """One form's display-ready stat block at the quoted level."""
    pct = growth_pct(curve)
    attack = sum(_leveled(hit, pct) for hit in (row[3], row[59], row[60]))
    return {
        "hp": _leveled(row[0], pct),
        "atk": attack,
        "dps": round(attack * 30 / frequency) if frequency else None,
        "freq": round(frequency / 30, 2) if frequency else None,
        "range": row[5],
        "speed": row[2],
        "kb": row[1],
        "cost": row[6] * 3 // 2,  # chapter-2 cost, the figure players know
        "recharge": round((row[7] * 2 + 2) / 30, 2),
        "area": bool(row[12]),
        "targets": [label for index, label in _TARGETS if row[index]],
        "effects": _effects(row),
        "immune": [label for index, label in _IMMUNITIES if row[index]],
    }


def build_stats(tarball: bytes, catstat: str, records: Iterable[Mapping] | None = None) -> dict:
    """The stats.json document for every catalogued unit found in the tarball."""
    records = load_records() if records is None else records
    frequencies = parse_frequencies(catstat)
    units = []
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:xz") as tar:
        curves = parse_curves(_member(tar, "DataLocal/unitlevel.csv"))
        for record in sorted(records, key=lambda record: record["id"]):
            unit_id = record["id"]
            text = _member(tar, f"DataLocal/unit{unit_id + 1:03d}.csv", optional=True)
            if text is None or unit_id >= len(curves):
                continue
            # A unit file can hold a stat row for a form that isn't released yet; the
            # catalogue's form list bounds what actually exists.
            rows = parse_stat_rows(text)[: len(record["forms"])]
            forms = [
                form_record(row, curves[unit_id], frequencies.get((unit_id, index)))
                for index, row in enumerate(rows)
            ]
            units.append({"id": unit_id, "forms": forms})

    return {
        "source": CATSTAT_URL,
        "fetched": date.today().isoformat(),
        "level": DISPLAY_LEVEL,
        "units": units,
    }


def load_stats(path: Path = STATS_PATH) -> dict:
    """The committed stats document."""
    return json.loads(path.read_text(encoding="utf-8"))


def refresh(tarball: bytes | None = None) -> int:
    """Rebuild stats.json from the live data feeds (or a pre-downloaded tarball);
    returns the unit count written."""
    if tarball is None:
        metadata = json.loads(_get(METADATA_URL))
        tarball = _get(release_url(metadata, latest_version(metadata)))
    catstat = _get(CATSTAT_URL).decode("utf-8", "replace")
    doc = build_stats(tarball, catstat)
    STATS_PATH.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    return len(doc["units"])
