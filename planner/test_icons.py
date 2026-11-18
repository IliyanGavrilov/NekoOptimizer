import urllib.error

import pytest

from planner import icons


def _records(*rows):
    return [{"id": unit_id, "forms": list(forms)} for unit_id, *forms in rows]


URL = "https://example.test/icon.png"


def test_wanted_pairs_each_unit_with_one_index_per_form():
    records = _records((5, "Base", "Evolved"), (7, "Only"))
    assert set(icons.wanted(records)) == {(5, 0), (5, 1), (7, 0)}


def test_an_egg_form_takes_its_egg_sprite():
    egg = {"id": 656, "forms": ["Ancient Egg", "Mystic Egg", "Haniwa Cat"], "eggs": [0, 1]}
    assert icons.source(egg, 1) == "https://battlecatsinfo.github.io/img/s/1/1.png"


def test_a_hatched_egg_form_takes_its_own_icon():
    egg = {"id": 656, "forms": ["Ancient Egg", "Mystic Egg", "Haniwa Cat"], "eggs": [0, 1]}
    assert icons.source(egg, 2) == "https://battlecatsinfo.github.io/img/u/656/2.png"


def test_fetch_writes_the_icon_under_its_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "_get", lambda url: b"PNG")
    assert icons.fetch(25, 2, URL, tmp_path) is True
    assert (tmp_path / "25" / "2.png").read_bytes() == b"PNG"


def test_fetch_leaves_an_icon_already_on_disk_alone(tmp_path, monkeypatch):
    path = tmp_path / "25"
    path.mkdir()
    (path / "0.png").write_bytes(b"kept")

    def refuse(url):
        raise AssertionError("re-fetched an icon already on disk")

    monkeypatch.setattr(icons, "_get", refuse)
    assert icons.fetch(25, 0, URL, tmp_path) is True
    assert (path / "0.png").read_bytes() == b"kept"


def test_fetch_reports_a_form_the_source_has_no_icon_for(tmp_path, monkeypatch):
    def missing(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(icons, "_get", missing)
    assert icons.fetch(25, 3, URL, tmp_path) is False


def test_fetch_raises_on_an_error_that_is_not_a_missing_icon(tmp_path, monkeypatch):
    def forbidden(url):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(icons, "_get", forbidden)
    with pytest.raises(urllib.error.HTTPError):
        icons.fetch(25, 0, URL, tmp_path)


def test_refresh_counts_the_icons_saved_and_the_ones_the_source_lacks(tmp_path, monkeypatch):
    def source(url):
        if url.endswith("/1.png"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return b"PNG"

    monkeypatch.setattr(icons, "_get", source)
    wanted = {(5, 0): "u/5/0.png", (5, 1): "u/5/1.png", (7, 0): "u/7/0.png"}
    assert icons.refresh(wanted, tmp_path, workers=2) == (2, 1)
