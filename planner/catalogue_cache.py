import time
from collections.abc import Callable
from functools import wraps

from django.db.models import F

from neko.region import current as active_region
from planner.models import CatalogueVersion

# How long a process trusts the version it last read before asking again: an import shows
# up within this, and a page view in between costs the database nothing at all.
VERSION_TTL = 60.0

_versions: dict[str, tuple[float, int]] = {}  # region -> (when read, version)
_reads: dict[tuple[str, str], tuple[int, object]] = {}  # (region, reader) -> (version, value)


def catalogue_version() -> int:
    """The active region's catalogue version, re-read at most once a VERSION_TTL."""
    region = active_region()
    now = time.monotonic()
    seen = _versions.get(region)
    if seen and now - seen[0] < VERSION_TTL:
        return seen[1]

    number = CatalogueVersion.objects.filter(region=region).values_list("number", flat=True)
    version = number.first() or 0
    _versions[region] = (now, version)

    return version


def bump_catalogue() -> None:
    """Mark the active region's catalogue changed: every process re-reads it within
    VERSION_TTL, this one at once."""
    region = active_region()
    CatalogueVersion.objects.get_or_create(region=region)
    CatalogueVersion.objects.filter(region=region).update(number=F("number") + 1)
    _versions.pop(region, None)


def forget_catalogue() -> None:
    """Drop everything this process holds, as if it had just started."""
    _versions.clear()
    _reads.clear()


def catalogue_cached[T](read: Callable[[], T]) -> Callable[[], T]:
    """Keep a catalogue read per region until the catalogue version moves. The units,
    cats and banners change only when an import runs, yet the heavy pages read thousands
    of their rows per view - the bulk of what the database sends out. The value is shared
    across requests: callers that decorate rows per visitor work on copies."""

    @wraps(read)
    def cached() -> T:
        key = (active_region(), read.__qualname__)
        version = catalogue_version()
        hit = _reads.get(key)
        if hit and hit[0] == version:
            return hit[1]

        value = read()
        _reads[key] = (version, value)

        return value

    return cached
