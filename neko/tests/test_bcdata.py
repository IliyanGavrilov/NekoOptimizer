import io
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from neko import bcdata
from neko.bcdata import catalogue_from_tarball, catalogue_records, latest_version, release_url
from neko.catalogue import Unit
from neko.models import Rarity

FIXTURES = Path(__file__).parent / "fixtures" / "bcdata"
UNITBUY = (FIXTURES / "unitbuy_head.csv").read_text(encoding="utf-8")
CAT_NAMES = (FIXTURES / "Unit_Explanation1_en.csv").read_text(encoding="utf-8")

METADATA = {
    "base_url": "http://host/",
    "versions": {"en": {"15.0.0": "a.tar.xz", "15.4.0": "b.tar.xz", "14.7.1": "c.tar.xz"}},
}


def make_tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as tar:
        for name, text in files.items():
            blob = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    return buffer.getvalue()


def test_latest_version_is_the_highest():
    assert latest_version(METADATA) == "15.4.0"


def test_release_url_joins_base_and_path():
    assert release_url(METADATA, "15.4.0") == "http://host/b.tar.xz"


def test_tarball_builds_a_unit():
    raw = make_tarball(
        {"./DataLocal/unitbuy.csv": UNITBUY, "./resLocal/Unit_Explanation1_en.csv": CAT_NAMES}
    )
    assert catalogue_from_tarball(raw)[0].name == "Cat"


def test_tarball_drops_units_with_no_name_file():
    raw = make_tarball({"./DataLocal/unitbuy.csv": UNITBUY})
    assert catalogue_from_tarball(raw) == {}


def test_records_are_sorted_by_id():
    catalogue = {2: Unit(2, ("B",), Rarity.RARE), 0: Unit(0, ("A",), Rarity.NORMAL)}
    assert [record["id"] for record in catalogue_records(catalogue)] == [0, 2]


class _Response(io.BytesIO):
    """A urlopen() result: a readable body used as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _urlopen(*failures):
    """A urlopen stand-in that raises each failure in turn, then serves a body."""
    attempts = iter(failures)

    def opener(request, timeout=None):
        failure = next(attempts, None)
        if failure is not None:
            raise failure

        return _Response(b"body")

    return opener


def test_a_timed_out_fetch_is_retried(monkeypatch):
    monkeypatch.setattr(bcdata.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen(TimeoutError()))
    assert bcdata._get("http://host/x") == b"body"


def test_a_throttled_fetch_is_retried(monkeypatch):
    throttled = urllib.error.HTTPError("http://host/x", 429, "Too Many", {}, None)
    monkeypatch.setattr(bcdata.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen(throttled))
    assert bcdata._get("http://host/x") == b"body"


def test_a_missing_file_is_not_retried(monkeypatch):
    missing = urllib.error.HTTPError("http://host/x", 404, "Nope", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen(missing))
    with pytest.raises(urllib.error.HTTPError):
        bcdata._get("http://host/x")
