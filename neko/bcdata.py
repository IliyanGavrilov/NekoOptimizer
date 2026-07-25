import http.client
import io
import json
import tarfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from neko.catalogue import Unit, build_catalogue, parse_forms, parse_rarities, parse_sets
from neko.region import DEFAULT_REGION, data_path, spec

# fieryhenry's maintained game-data mirror. The old GitHub BCData repo is archived and
# frozen at 14.7.0; this Forgejo keeps publishing each new game version as a tarball.
BCDATA_BASE = "https://git.battlecatsmodding.org/fieryhenry/BCData"
METADATA_URL = f"{BCDATA_BASE}/raw/metadata.json"

UNITS_FILE = "units.json"


def units_path(region: str | None = None) -> Path:
    """Where one region's committed catalogue lives."""
    return data_path(UNITS_FILE, region)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def latest_version(metadata: Mapping, region: str = DEFAULT_REGION) -> str:
    """The newest published version for a region, from metadata.json."""
    return max(metadata["versions"][region], key=_version_key)


def release_url(metadata: Mapping, version: str, region: str = DEFAULT_REGION) -> str:
    """The download URL of one version's data tarball."""
    return metadata["base_url"] + metadata["versions"][region][version]


def catalogue_from_tarball(raw: bytes, region: str = DEFAULT_REGION) -> dict[int, Unit]:
    """Build the unit catalogue from a BCData version tarball (xz-compressed)."""
    locale = spec(region).locale
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as tar:
        rarities = parse_rarities(_member(tar, "DataLocal/unitbuy.csv"))
        picture_book = _member(tar, f"resLocal/nyankoPictureBook_{locale}.csv", optional=True)
        sets = parse_sets(picture_book, region) if picture_book else {}

        forms = {}
        for unit_id in rarities:
            name = f"resLocal/Unit_Explanation{unit_id + 1}_{locale}.csv"
            text = _member(tar, name, optional=True)
            if text is not None:
                forms[unit_id] = parse_forms(text, region)

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


# One region's schedule refresh pulls several hundred files from the same host in
# sequence, so the odd read timeout or throttle reply is routine - back off and retry
# those rather than losing the whole run to one blip.
_RETRIES = 4
_RETRY_CODES = frozenset({429, 500, 502, 503, 504})
_BACKOFF = 3  # seconds, times the attempt number


def _get(url: str) -> bytes:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"refusing to fetch non-HTTP URL: {url!r}")

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, _RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
                return response.read()
        except urllib.error.HTTPError as error:
            if attempt == _RETRIES or error.code not in _RETRY_CODES:
                raise
        except urllib.error.URLError, TimeoutError, http.client.HTTPException:
            if attempt == _RETRIES:
                raise

        time.sleep(_BACKOFF * attempt)


def download_catalogue(region: str = DEFAULT_REGION) -> tuple[str, dict[int, Unit]]:
    """Fetch the newest catalogue from the live mirror; returns its version and the units."""
    metadata = json.loads(_get(METADATA_URL))
    version = latest_version(metadata, region)
    raw = _get(release_url(metadata, version, region))

    return version, catalogue_from_tarball(raw, region)


@cache
def _read(path: Path) -> list[dict]:
    """The catalogue records previously written to units.json. Memoized: the committed file
    only changes on a re-import (a fresh process), and every caller treats it read-only."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(region: str | None = None) -> list[dict]:
    """One region's committed catalogue records."""
    return _read(units_path(region))
