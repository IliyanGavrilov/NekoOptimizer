import json

import pytest

from neko.normal_plan import plan_normal
from planner.forms import MIN_SEEK_ROLLS
from planner.models import Seed
from planner.services import build_normal_plan

# Every request reads the persisted region row (planner.middleware.region_scope).
pytestmark = [pytest.mark.django_db, pytest.mark.urls("planner.reference_urls")]

# The ampuri-verified golden seed the engine fixtures use: on Normal Capsules its
# cell 1A is Fish Cat, and with Fish Cat as the remembered last pull that cell
# dupes into Bird Cat (see neko/tests/fixtures/normal_golden_lastcat.json).
SEED = 1515525936

EIGHT_ROLLS = ["0:0", "0:1", "0:2", "0:3", "0:4", "0:5", "0:6", "0:7"]


def test_normal_page_opens_on_the_stored_normal_seed(client, profile):
    Seed.store(profile, SEED, Seed.NORMAL, last="Fish Cat")
    Seed.store(profile, 7)
    content = client.get("/normal/").content.decode()
    assert f'data-saved="{SEED}" data-saved-last="Fish Cat"' in content


def test_normal_page_offers_machines_finder_and_planner(client):
    content = client.get("/normal/").content.decode()

    assert "Normal Capsules" in content
    assert "Catseye Capsules" in content
    # The plain capsule's two flavors are machine picks of their own (normal.js keeps
    # them exclusive), with no separate Superfeline toggle.
    assert 'value="n"' in content and 'value="np"' in content
    assert "Superfeline unlocked" not in content
    assert "normalPools" in content
    assert "normalPlanPanel" in content
    assert "Normal Cat Tickets" in content  # one stash feeds normal/catfruit/catseye
    assert "Dark Catseyes" in content  # the default plan target

    pools = content.split("normalPools")[1]
    for unseekable in ("Lucky Ticket", "Catfruit Capsules", "Catseye Capsules"):
        assert unseekable not in pools  # only the plain capsules are seekable


@pytest.mark.django_db
def test_normal_tracks_roll_the_chosen_machines(client):
    response = client.post(
        "/reference/normal/tracks/", {"seed": SEED, "banners": ["n", "ce"], "track_length": 20}
    )
    content = response.content.decode()

    assert "Fish Cat" in content  # 1A on Normal Capsules
    assert "Catseye Capsules" in content  # the legend names both machines
    assert "if dupe:" in content  # realized dupe branches render
    assert 'data-seed="4190409564"' in content  # 1A's dice: the state after it


@pytest.mark.django_db
def test_normal_tracks_remember_the_last_item(client):
    response = client.post(
        "/reference/normal/tracks/",
        {"seed": SEED, "banners": ["n"], "track_length": 5, "last_item": "Fish Cat"},
    )
    content = response.content.decode()

    # The remembered pull dupes 1A: its branch (Bird Cat, landing 2B) must show.
    assert "Bird Cat" in content
    assert "jumps to 2B" in content


@pytest.mark.django_db
def test_normal_tracks_need_a_seed_and_a_machine(client):
    assert client.post("/reference/normal/tracks/", {"seed": "junk"}).content == b""
    content = client.post("/reference/normal/tracks/", {"seed": SEED}).content.decode()
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


def test_normal_seek_start_hands_back_the_search_for_the_page(client):
    data = client.post("/normal/seek/start/", {"banner": "n", "rolls": EIGHT_ROLLS}).json()

    assert data["cats"] == [[0, slot] for slot in range(8)]
    assert data["rerollable"] == [0]
    # The dupe memory the "show my rolls" button carries: 0:7 is Lizard Cat.
    assert data["last_cat"] == "Lizard Cat"


# The ce grid shows a Dark Catseye at 15B for this seed (see test_normal_plan).
PLAN_SEED = 2157514271


@pytest.mark.django_db
def test_normal_plan_lights_a_path(client):
    expected = plan_normal(PLAN_SEED, [(30, ("ce",))], frozenset({"Dark Catseye"}))
    assert expected.hits  # the fixture seed must actually reach a dark

    response = client.post(
        "/reference/normal/plan/",
        {
            "seed": PLAN_SEED,
            "banners": ["ce"],
            "tickets": json.dumps({"normal": 30}),
            "target": "dark",
            "track_length": 20,
        },
    )
    content = response.content.decode()

    assert f"<strong>{expected.hits}</strong> Dark Catseyes" in content
    assert "Apply this plan" in content  # the apply button carries the end state
    assert f'data-seed="{expected.seed_after}"' in content
    # ...and what it spends, keyed by the budget field it comes off.
    assert f'data-normal="{len(expected.steps)}"' in content
    assert "data-lucky=" not in content
    assert 'class="item dark-catseye got"' in content  # the collected dark is gilded


def test_normal_plan_splits_a_long_run_into_ten_pull_steps():
    plan = build_normal_plan(PLAN_SEED, ["ce"], {"normal": 30}, "dark", 20)
    pulls = len(plan_normal(PLAN_SEED, [(30, ("ce",))], frozenset({"Dark Catseye"})).steps)
    assert pulls == 15  # one machine all the way: a single run before splitting

    assert [len(leg["pulls"]) for leg in plan["legs"]] == [10, 5]
    assert [leg["n"] for leg in plan["legs"]] == [1, 2]
    assert [leg["cost_text"] for leg in plan["legs"]] == [
        "10 Normal Cat Tickets",
        "5 Normal Cat Tickets",
    ]


def test_a_lucky_stash_walks_the_track_on_its_hidden_machine():
    """Lucky tickets never roll a Catseye, so by default they pay for the walking pulls -
    on their machine even with its column off, which the plan's table then shows."""
    tickets = {"normal": 30, "lucky": 30}
    plan = build_normal_plan(PLAN_SEED, ["ce"], tickets, "dark", 20)
    spent = {s["kind"]: s["rolls"] for s in plan["spent"]}

    assert spent["lucky"] > spent["normal"]
    assert [b["name"] for b in plan["track"]["legend"]] == ["Catseye Capsules", "Lucky Ticket"]

    keep_lucky = build_normal_plan(PLAN_SEED, ["ce"], tickets, "dark", 20, moves="normal")
    assert keep_lucky["hits"] == plan["hits"]
    assert {s["kind"]: s["rolls"] for s in keep_lucky["spent"]}["normal"] > spent["normal"]


@pytest.mark.django_db
def test_normal_plan_reports_an_unreachable_target(client):
    # One catseye roll from a cell that isn't a dark: nothing to collect.
    response = client.post(
        "/reference/normal/plan/",
        {
            "seed": 1515525936,
            "banners": ["ce"],
            "tickets": json.dumps({"normal": 1}),
            "target": "dark",
        },
    )

    assert b"No Dark Catseyes reachable" in response.content


def test_normal_plan_rejects_bad_posts(client):
    def plan(**fields):
        fields.setdefault("banners", ["ce"])
        return client.post("/reference/normal/plan/", fields).status_code

    assert plan(seed="junk", tickets='{"normal": 5}', target="dark") == 400
    assert plan(seed=PLAN_SEED, tickets="{}", target="dark") == 400
    assert plan(seed=PLAN_SEED, tickets='{"gold": 5}', target="dark") == 400
    assert plan(seed=PLAN_SEED, tickets='{"normal": 5}', target="dark", banners=[]) == 400
    assert plan(seed=PLAN_SEED, tickets='{"normal": 5}', target="nonsense") == 400
    assert plan(seed=PLAN_SEED, tickets='{"normal": 5}', target="item:Not A Thing") == 400


@pytest.mark.parametrize(
    "path", ["/reference/normal/tracks/", "/normal/seek/start/", "/reference/normal/plan/"]
)
def test_normal_posts_reject_get(client, path):
    assert client.get(path).status_code == 405


def test_the_normal_seed_box_says_which_seed_and_opens_its_finder(client):
    content = client.get("/normal/").content.decode()
    assert "Normal Capsule</strong> seed" in content
    assert 'href="#normalFinder" class="seed-find"' in content
