import time

import pytest

from neko.models import Banner as RollBanner
from neko.models import Rarity
from neko.seek import SeekMatch, SeekResult
from planner.forms import MIN_SEEK_ROLLS

BANNER = RollBanner(
    "test-run",
    "Test Banner",
    "",
    {Rarity.RARE: 7000, Rarity.SUPER_RARE: 2500, Rarity.UBER_SUPER_RARE: 500},
    {
        Rarity.RARE: ("Rare A", "Rare B", "Rare C"),
        Rarity.SUPER_RARE: ("Super A",),
        Rarity.UBER_SUPER_RARE: ("Uber A", "Uber B"),
    },
)

FIVE_ROLLS = ["0:0", "0:1", "0:2", "1:0", "2:1"]


@pytest.fixture
def banner(monkeypatch):
    monkeypatch.setattr("planner.views.seek_banner", lambda selection: BANNER)
    return BANNER


def wait_done(client, job):
    for _ in range(200):
        data = client.get(f"/seek/status/?job={job}").json()
        if data["done"]:
            return data

        time.sleep(0.01)

    raise AssertionError("seek job never finished")


@pytest.mark.django_db
def test_seed_finder_page_lists_banner_runs(client):
    content = client.get("/seek/").content

    assert b"Seed Finder" in content
    assert b"seekBanner" in content


def test_seek_pool_groups_the_banners_cats(client, banner):
    data = client.get("/seek/pool/?banner=whatever").json()

    assert data["name"] == "Test Banner"
    assert [g["rarity"] for g in data["groups"]] == ["Rare", "Super Rare", "Uber Super Rare"]
    assert data["groups"][0]["options"][1] == {"value": "0:1", "label": "Rare B"}


def test_seek_pool_rejects_an_unknown_banner(client, monkeypatch):
    monkeypatch.setattr("planner.views.seek_banner", lambda selection: None)

    assert client.get("/seek/pool/?banner=nope").status_code == 400


def test_seek_start_needs_enough_rolls(client, banner):
    response = client.post("/seek/start/", {"banner": "x", "rolls": FIVE_ROLLS[:2]})

    assert response.status_code == 400
    assert str(MIN_SEEK_ROLLS) in response.content.decode()


@pytest.mark.parametrize("bad", ["9:0", "0:99", "junk", "0:-1"])
def test_seek_start_rejects_malformed_rolls(client, banner, bad):
    rolls = [*FIVE_ROLLS[:-1], bad]

    assert client.post("/seek/start/", {"banner": "x", "rolls": rolls}).status_code == 400


def test_seek_start_polls_to_matches(client, banner, monkeypatch):
    result = SeekResult((SeekMatch(seed_before=11, seed_after=22, run=0),))
    monkeypatch.setattr("planner.seekjobs.seek_seed", lambda b, observed, progress=None: result)

    job = client.post("/seek/start/", {"banner": "x", "rolls": FIVE_ROLLS}).json()["job"]
    data = wait_done(client, job)

    assert data["matches"] == [{"seed_before": 11, "seed_after": 22, "run": 0}]
    assert data["truncated"] is False
    assert data["error"] == ""
    # The dupe memory the "open at your position" link carries: 2:1 is Uber B.
    assert data["last_cat"] == "Uber B"


def test_seek_start_surfaces_a_search_error(client, banner, monkeypatch):
    def boom(b, observed, progress=None):
        raise ValueError("bad window")

    monkeypatch.setattr("planner.seekjobs.seek_seed", boom)

    job = client.post("/seek/start/", {"banner": "x", "rolls": FIVE_ROLLS}).json()["job"]
    data = wait_done(client, job)

    assert data["error"] == "bad window"
    assert "matches" not in data


def test_seek_status_rejects_an_unknown_job(client):
    assert client.get("/seek/status/?job=nope").status_code == 400
