import urllib.error

import pytest

from planner import icons


def _records(*rows):
    return [{"id": unit_id, "forms": list(forms)} for unit_id, *forms in rows]


def test_wanted_pairs_each_unit_with_one_index_per_form():
    records = _records((5, "Base", "Evolved"), (7, "Only"))
    assert icons.wanted(records) == {(5, 0), (5, 1), (7, 0)}


def test_fetch_writes_the_icon_under_its_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "_get", lambda url: b"PNG")
    assert icons.fetch(25, 2, tmp_path) is True
    assert (tmp_path / "25" / "2.png").read_bytes() == b"PNG"


def test_fetch_leaves_an_icon_already_on_disk_alone(tmp_path, monkeypatch):
    path = tmp_path / "25"
    path.mkdir()
    (path / "0.png").write_bytes(b"kept")

    def refuse(url):
        raise AssertionError("re-fetched an icon already on disk")

    monkeypatch.setattr(icons, "_get", refuse)
    assert icons.fetch(25, 0, tmp_path) is True
    assert (path / "0.png").read_bytes() == b"kept"


def test_fetch_reports_a_form_the_source_has_no_icon_for(tmp_path, monkeypatch):
    def missing(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(icons, "_get", missing)
    assert icons.fetch(25, 3, tmp_path) is False


def test_fetch_raises_on_an_error_that_is_not_a_missing_icon(tmp_path, monkeypatch):
    def forbidden(url):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(icons, "_get", forbidden)
    with pytest.raises(urllib.error.HTTPError):
        icons.fetch(25, 0, tmp_path)


def test_refresh_counts_the_icons_saved_and_the_ones_the_source_lacks(tmp_path, monkeypatch):
    def source(url):
        if url.endswith("/1.png"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return b"PNG"

    monkeypatch.setattr(icons, "_get", source)
    assert icons.refresh([(5, 0), (5, 1), (7, 0)], tmp_path, workers=2) == (2, 1)
