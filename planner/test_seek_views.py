import pytest

from neko.models import Banner as RollBanner
from neko.models import Rarity
from planner.forms import MIN_SEEK_ROLLS

# Every request reads the persisted region row (planner.middleware.region_scope).
pytestmark = pytest.mark.django_db

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


def test_seek_start_hands_back_the_search_for_the_page(client, banner):
    data = client.post("/seek/start/", {"banner": "x", "rolls": FIVE_ROLLS}).json()

    assert data["cats"] == [[0, 0], [0, 1], [0, 2], [1, 0], [2, 1]]
    assert data["bands"] == [0, 7000, 9500, 10000, 10000]
    assert data["sizes"] == [3, 1, 2, 0]
    assert data["rerollable"] == [0]
    # The dupe memory the "open at your position" link carries: 2:1 is Uber B.
    assert data["last_cat"] == "Uber B"
