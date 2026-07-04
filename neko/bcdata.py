import io
import json
import tarfile
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from neko.catalogue import Unit, build_catalogue, parse_forms, parse_rarities, parse_sets

# fieryhenry's maintained game-data mirror. The old GitHub BCData repo is archived and
# frozen at 14.7.0; this Forgejo keeps publishing each new game version as a tarball.
BCDATA_BASE = "https://git.battlecatsmodding.org/fieryhenry/BCData"
METADATA_URL = f"{BCDATA_BASE}/raw/metadata.json"

UNITS_PATH = Path(__file__).parent / "data" / "units.json"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def latest_version(metadata: Mapping, country: str = "en") -> str:
    """The newest published version for a country, from metadata.json."""
    return max(metadata["versions"][country], key=_version_key)


def release_url(metadata: Mapping, version: str, country: str = "en") -> str:
    """The download URL of one version's data tarball."""
    return metadata["base_url"] + metadata["versions"][country][version]


def catalogue_from_tarball(raw: bytes) -> dict[int, Unit]:
    """Build the unit catalogue from a BCData version tarball (xz-compressed)."""
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as tar:
        rarities = parse_rarities(_member(tar, "DataLocal/unitbuy.csv"))
        picture_book = _member(tar, "resLocal/nyankoPictureBook_en.csv", optional=True)
        sets = parse_sets(picture_book) if picture_book else {}
        forms = {}
        for unit_id in rarities:
            text = _member(tar, f"resLocal/Unit_Explanation{unit_id + 1}_en.csv", optional=True)
            if text is not None:
                forms[unit_id] = parse_forms(text)
    return build_catalogue(rarities, forms, sets)


def _member(tar: tarfile.TarFile, path: str, optional: bool = False) -> str | None:
    """Read one file out of the tarball; tarball entries are rooted at ``./``."""
    try:
        handle = tar.extractfile(f"./{path}")
    except KeyError:
        handle = None
    if handle is None:
        if optional:
            return None
        raise KeyError(path)
    return handle.read().decode("utf-8", "replace")


def catalogue_records(catalogue: Mapping[int, Unit]) -> list[dict]:
    """The catalogue as id-sorted JSON records for units.json."""
    return [
        {
            "id": unit.unit_id,
            "name": unit.name,
            "rarity": unit.rarity.value,
            "forms": list(unit.forms),
            "set": unit.set_name,
        }
        for unit in sorted(catalogue.values(), key=lambda unit: unit.unit_id)
    ]


def _get(url: str) -> bytes:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"refusing to fetch non-HTTP URL: {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
        return response.read()


def download_catalogue(country: str = "en") -> tuple[str, dict[int, Unit]]:
    """Fetch the newest catalogue from the live mirror; returns its version and the units."""
    metadata = json.loads(_get(METADATA_URL))
    version = latest_version(metadata, country)
    raw = _get(release_url(metadata, version, country))
    return version, catalogue_from_tarball(raw)


def load_records(path: Path = UNITS_PATH) -> list[dict]:
    """The catalogue records previously written to units.json."""
    return json.loads(path.read_text(encoding="utf-8"))
