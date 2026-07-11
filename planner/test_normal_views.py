import time

import pytest

from neko.seek import SeekMatch, SeekResult
from planner.forms import MIN_SEEK_ROLLS

# The ampuri-verified golden seed the engine fixtures use: on Normal Capsules its
# cell 1A is Fish Cat, and with Fish Cat as the remembered last pull that cell
# dupes into Bird Cat (see neko/tests/fixtures/normal_golden_lastcat.json).
SEED = 1515525936

EIGHT_ROLLS = ["0:0", "0:1", "0:2", "0:3", "0:4", "0:5", "0:6", "0:7"]


def wait_done(client, job):
    for _ in range(200):
        data = client.get(f"/seek/status/?job={job}").json()
        if data["done"]:
            return data

        time.sleep(0.01)

    raise AssertionError("seek job never finished")


def test_normal_page_offers_machines_and_finder(client):
    content = client.get("/normal/").content.decode()

    assert "Normal Capsules" in content
    assert "Catseye Capsules" in content
    assert "nseekBanner" in content
    assert "normalPools" in content
    assert "Lucky Ticket" not in content.split("normalPools")[1]  # not seekable


def test_normal_tracks_roll_the_chosen_machines(client):
    response = client.post(
        "/normal/tracks/", {"seed": SEED, "banners": ["n", "ce"], "track_length": 20}
    )
    content = response.content.decode()

    assert "Fish Cat" in content  # 1A on Normal Capsules
    assert "Catseye Capsules" in content  # the legend names both machines
    assert "if dupe:" in content  # realized dupe branches render
    assert 'data-seed="4190409564"' in content  # 1A's dice: the state after it


def test_normal_tracks_remember_the_last_item(client):
    response = client.post(
        "/normal/tracks/",
        {"seed": SEED, "banners": ["n"], "track_length": 5, "last_item": "Fish Cat"},
    )
    content = response.content.decode()

    # The remembered pull dupes 1A: its branch (Bird Cat, landing 2B) must show.
    assert "Bird Cat" in content
    assert "jumps to 2B" in content


def test_normal_tracks_need_a_seed_and_a_machine(client):
    assert client.post("/normal/tracks/", {"seed": "junk"}).content == b""
    content = client.post("/normal/tracks/", {"seed": SEED}).content.decode()
    assert "at least one capsule machine" in content


def test_normal_seek_start_rejects_bad_posts(client):
    def start(banner, rolls):
        return client.post("/normal/seek/start/", {"banner": banner, "rolls": rolls}).status_code

    assert start("lt", EIGHT_ROLLS) == 400  # duplicate-name pools aren't seekable
    assert start("n", ["junk"]) == 400
    assert start("n", ["0:99"]) == 400
    assert start("ce", ["9:0"]) == 400

    short = client.post("/normal/seek/start/", {"banner": "n", "rolls": EIGHT_ROLLS[:2]})
    assert short.status_code == 400
    assert str(MIN_SEEK_ROLLS) in short.content.decode()


def test_normal_seek_start_polls_to_matches(client, monkeypatch):
    result = SeekResult((SeekMatch(seed_before=11, seed_after=22, run=0),))
    monkeypatch.setattr(
        "planner.seekjobs.seek_normal", lambda banner, observed, progress=None: result
    )

    job = client.post("/normal/seek/start/", {"banner": "n", "rolls": EIGHT_ROLLS}).json()["job"]
    data = wait_done(client, job)

    assert data["matches"] == [{"seed_before": 11, "seed_after": 22, "run": 0}]
    assert data["truncated"] is False
    # The dupe memory the "show my rolls" button carries: 0:7 is Lizard Cat.
    assert data["last_cat"] == "Lizard Cat"


@pytest.mark.parametrize("path", ["/normal/tracks/", "/normal/seek/start/"])
def test_normal_posts_reject_get(client, path):
    assert client.get(path).status_code == 405
