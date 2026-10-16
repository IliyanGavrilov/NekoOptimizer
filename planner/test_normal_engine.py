import json
import random

import pytest

from neko.normal import NORMAL_BANNERS, play
from planner.test_tracks_engine import _same, catalogue  # noqa: F401

# The reference normal views are routed only for tests (planner.reference_urls).
pytestmark = [pytest.mark.django_db, pytest.mark.urls("planner.reference_urls")]

RNG = random.Random(20261018)  # nosec B311
ALL = [banner.key for banner in NORMAL_BANNERS]
# The ce grid shows a Dark Catseye at 15B for this seed (see test_normal_plan).
DARK_SEED = 2157514271


def _compare(client, engine, kind, data):
    if kind == "plan":
        expected = client.post("/reference/normal/plan/", data).content.decode()
        request = client.post("/normal/plan/", data).json()
    else:
        expected = client.post("/reference/normal/tracks/", data).content.decode()
        request = client.post("/normal/tracks/", data).json()
    expected, actual = _same(expected), _same(engine(request))
    if expected == actual:
        return expected
    at = next(
        (i for i, (a, b) in enumerate(zip(expected, actual, strict=False)) if a != b),
        min(len(expected), len(actual)),
    )
    around = slice(max(at - 200, 0), at + 200)
    pytest.fail(
        f"{kind} differs at {at}:\n  django: {expected[around]}\n  engine: {actual[around]}"
    )


def _tracks(seed, machines, rows="100", last=""):
    return {"seed": str(seed), "banners": machines, "track_length": rows, "last_item": last}


@pytest.mark.parametrize(
    "machines", [["n"], ["np", "n"], ["ce"], ["cf", "lt"], ALL, list(reversed(ALL))]
)
def test_normal_tables_match(client, engine, catalogue, machines):  # noqa: F811
    html = _compare(client, engine, "tracks", _tracks(RNG.getrandbits(32), machines))
    assert "normal-track" in html


@pytest.mark.parametrize("rows", ["1", "300"])
def test_normal_tables_match_at_any_length(client, engine, catalogue, rows):  # noqa: F811
    _compare(client, engine, "tracks", _tracks(RNG.getrandbits(32), ALL, rows))


def test_a_normal_table_dupes_on_the_remembered_last_pull(client, engine, catalogue):  # noqa: F811
    banner = NORMAL_BANNERS[0]
    for seed in (RNG.getrandbits(32) for _ in range(500)):
        first, _ = play(seed, banner, 1)
        break
    html = _compare(client, engine, "tracks", _tracks(seed, ["n", "lt"], last=first[0]))
    assert "if dupe" in html


def test_an_empty_normal_table_says_so(client, engine, catalogue):  # noqa: F811
    _compare(client, engine, "tracks", _tracks(1, []))


def _plan(seed, machines, target, tickets, last=""):
    return {
        **_tracks(seed, machines, "100", last),
        "target": target,
        "tickets": json.dumps(tickets),
    }


@pytest.mark.parametrize(
    ("target", "tickets"),
    [
        ("dark", {"normal": 30}),
        ("dark", {"normal": 20, "lucky": 3, "luckyg": 2}),
        ("upgrades", {"normal": 15, "lucky": 4}),
        ("cats", {"normal": 10}),
        ("lil", {"lucky": 5, "luckyg": 5}),
        ("item:Dark Catseye", {"normal": 40, "lucky": 2}),
    ],
)
def test_normal_plans_match(client, engine, catalogue, target, tickets):  # noqa: F811
    _compare(client, engine, "plan", _plan(DARK_SEED, ["ce", "n", "lt", "ltg"], target, tickets))


def test_a_normal_plan_that_finds_nothing_matches(client, engine, catalogue):  # noqa: F811
    html = _compare(client, engine, "plan", _plan(DARK_SEED, ["n"], "dark", {"normal": 3}))
    assert "seek-none" in html


@pytest.mark.parametrize("seed", [RNG.getrandbits(32) for _ in range(4)])
def test_normal_plans_match_on_random_seeds(client, engine, catalogue, seed):  # noqa: F811
    machines = RNG.sample(ALL, RNG.randint(1, len(ALL)))
    tickets = {
        "normal": RNG.randint(0, 40),
        "lucky": RNG.randint(0, 6),
        "luckyg": RNG.randint(0, 6),
    }
    target = RNG.choice(["dark", "upgrades", "cats", "lil"])
    _compare(client, engine, "plan", _plan(seed, machines, target, tickets))


def test_a_normal_plan_collects_the_dark_catseye(client, engine, catalogue):  # noqa: F811
    html = _compare(client, engine, "plan", _plan(DARK_SEED, ["ce"], "dark", {"normal": 30}))
    assert "plan-haul" in html and "step-get dark-catseye" in html
