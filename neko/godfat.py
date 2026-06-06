from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from neko.models import Rarity

_PAW = "\U0001f43e"  # godfat appends a paw glyph to every cat name
_PICK = re.compile(r"pick\('(\d+)([AB])'\)")
_RARITY_BY_CLASS = {
    "rare": Rarity.RARE,
    "supa": Rarity.SUPER_RARE,
    "uber": Rarity.UBER_SUPER_RARE,
    "legend": Rarity.LEGEND_RARE,
    "exclusive": Rarity.UBER_SUPER_RARE,
}


@dataclass(frozen=True, slots=True)
class TrackPull:
    """A pull outcome on track "A" or "B" at a 1-based position."""

    position: int
    track: str
    cat: str
    rarity: Rarity


def _rarity_from_classes(classes: list[str]) -> Rarity | None:
    for cls in classes:
        base = cls.removesuffix("_fest")
        if base in _RARITY_BY_CLASS:
            return _RARITY_BY_CLASS[base]
    return None


def parse_rolls(html: str) -> list[TrackPull]:
    """Extract every result cell, sorted by (position, track). O(cells)."""
    soup = BeautifulSoup(html, "html.parser")
    pulls = []
    for cell in soup.select("td.cat.pick"):
        match = _PICK.search(cell.get("onclick", ""))
        rarity = _rarity_from_classes(cell.get("class", []))
        if match is None or rarity is None:
            continue
        cat = cell.get_text(strip=True).replace(_PAW, "").strip()
        pulls.append(TrackPull(int(match.group(1)), match.group(2), cat, rarity))
    pulls.sort(key=lambda pull: (pull.position, pull.track))
    return pulls
