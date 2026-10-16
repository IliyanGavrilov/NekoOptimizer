import json
import random

import pytest

from neko.gachadata import load_events
from neko.roller import prepare_selected, roll_selected
from neko.tests.test_seek import GOLDEN_SEED
from planner.services import engine_request

RNG = random.Random(20261016)


def _runs(count):
    """A spread of real runs: every rare-gacha shape the schedule has had."""
    events = load_events()
    return [f"{e.start}|{e.name}" for e in RNG.sample(events, count)]


CASES = [
    (GOLDEN_SEED, _runs(4), "", 0),
    (RNG.getrandbits(32), _runs(5), "", 11),
    (RNG.getrandbits(32), _runs(3), "", 15),
    *((RNG.getrandbits(32), _runs(2), "", 0) for _ in range(6)),
]


def _python(rolls):
    def rows(pulls):
        return [
            [
                p.position,
                "AB".index(p.track),
                p.cat,
                ["Rare", "Super Rare", "Uber Super Rare", "Legend Rare"].index(p.rarity),
                p.seed,
                p.steps,
                p.realized,
                p.rarity_seed,
            ]
            for p in pulls
        ]

    return {
        name: {
            "pulls": rows(r.pulls),
            "rerolls": rows(r.rerolls),
            "guaranteed": rows(r.guaranteed),
            "guaranteed_rerolls": rows(r.guaranteed_rerolls),
        }
        for name, r in rolls.banners.items()
    }


def _compare(engine, seed, runs, last_cat="", guaranteed=0, future=None):
    options = {"simulate_guaranteed": guaranteed, "future_ubers": future}
    prepared = prepare_selected(runs, **options)
    expected = _python(roll_selected(seed, runs, count=300, last_cat=last_cat, **options))
    assert json.loads(engine(engine_request("rolls", seed, prepared, 300, last_cat))) == expected


@pytest.mark.parametrize(("seed", "runs", "last_cat", "guaranteed"), CASES)
def test_engine_rolls_exactly_like_the_python_roller(engine, seed, runs, last_cat, guaranteed):
    _compare(engine, seed, runs, last_cat, guaranteed)


def test_engine_dupes_the_first_cell_on_the_remembered_last_pull(engine):
    runs = _runs(3)
    for seed in (RNG.getrandbits(32) for _ in range(400)):
        first = roll_selected(seed, runs, count=1).banners
        rare = next((r.pulls[0].cat for r in first.values() if r.pulls[0].rarity == "Rare"), "")
        if rare:
            break
    _compare(engine, seed, runs, last_cat=rare)


def test_engine_rolls_future_uber_placeholders_like_the_roller(engine):
    runs = _runs(2)
    name = runs[0].partition("|")[2]
    _compare(engine, RNG.getrandbits(32), runs, future={name: 3})
