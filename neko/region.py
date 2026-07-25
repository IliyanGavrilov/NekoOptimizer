# The four published game versions. The roll mechanics are identical everywhere - only
# the data differs: each version ships its own catalogue, gacha schedule and pools, and
# its own localized text, so every committed data file is region-scoped.

import contextlib
import contextvars
from dataclasses import dataclass
from pathlib import Path

DATA_ROOT = Path(__file__).parent / "data"
DEFAULT_REGION = "en"


@dataclass(frozen=True, slots=True)
class RegionSpec:
    """One game version: its code, the label the switcher shows, the locale suffix its
    tarball's resLocal files carry, and the separator those files use - the Japanese
    feed is comma-separated where every other version is pipe-separated."""

    code: str
    label: str
    locale: str
    separator: str


REGIONS = (
    RegionSpec("en", "English", "en", "|"),
    RegionSpec("jp", "Japan", "ja", ","),
    RegionSpec("tw", "Taiwan", "tw", "|"),
    RegionSpec("kr", "Korea", "ko", "|"),
)

_BY_CODE = {region.code: region for region in REGIONS}
CODES = tuple(_BY_CODE)

_active = contextvars.ContextVar("neko_region", default=DEFAULT_REGION)


def current() -> str:
    """The active region code."""
    return _active.get()


def spec(code: str | None = None) -> RegionSpec:
    """One region's metadata (the active region's when omitted)."""
    return _BY_CODE[code or current()]


@contextlib.contextmanager
def using(code: str):
    """Make *code* the active region for the block - what scopes a request, a management
    command, or a test to one game version."""
    if code not in _BY_CODE:
        raise ValueError(f"unknown region: {code!r}")

    token = _active.set(code)
    try:
        yield code
    finally:
        _active.reset(token)


def data_path(name: str, code: str | None = None) -> Path:
    """The path of one region-scoped data file, e.g. ``neko/data/en/units.json``."""
    return DATA_ROOT / (code or current()) / name
