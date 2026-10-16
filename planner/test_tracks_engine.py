import json
import random
import re
from collections import defaultdict

import pytest

from neko.gachadata import load_events
from neko.roller import prepare_selected, roll_selected, units_from_records
from neko.tests.test_seek import GOLDEN_SEED
from planner.models import Cat, Unit

# Every request reads the persisted region row (planner.middleware.region_scope).
pytestmark = [pytest.mark.django_db, pytest.mark.urls("planner.reference_urls")]

RNG = random.Random(1016)  # nosec B311
EVENTS = load_events()


def _runs(count):
    return [f"{e.start}|{e.name}" for e in RNG.sample(EVENTS, count)]


def _twins():
    """Two banner names over one pool, rates and guarantee: rolls the engine must merge."""
    by_pool = defaultdict(dict)
    for e in EVENTS:
        by_pool[(e.pool_id, e.rare, e.supa, e.uber, e.guaranteed, e.step_up)].setdefault(e.name, e)
    runs = next(list(named.values()) for named in by_pool.values() if len(named) > 1)
    return [f"{e.start}|{e.name}" for e in runs[:2]]


def _same(html):
    """The markup with whitespace runs collapsed: what both renderers must agree on."""
    return re.sub(r"\s+", " ", html).strip()


@pytest.fixture
def catalogue(profile):
    """Units for every rollable name (real ids, so tier badges and icons show), with a few
    owned and wishlisted, as a returning player's table would carry them."""
    records = units_from_records()
    Unit.objects.bulk_create(
        Unit(unit_id=uid, name=name, rarity=rarity) for uid, (name, rarity) in records.items()
    )
    units = list(Unit.objects.order_by("unit_id"))
    profile.owned.add(*units[::7])
    profile.wanted.add(*units[3::11])
    return profile


def _post(client, path, data):
    return client.post(path, data)


def _compare(client, engine, data):
    html = _post(client, "/tracks/", data).content.decode()
    request = _post(client, "/tracks/engine/", data).json()
    got = engine(request)
    expected, actual = _same(html), _same(got)
    if expected == actual:
        return expected
    at = next(i for i, (a, b) in enumerate(zip(expected, actual, strict=False)) if a != b)
    around = slice(max(at - 150, 0), at + 150)
    pytest.fail(f"differs at {at}:\n  django: {expected[around]}\n  engine: {actual[around]}")


def _form(seed, runs, **extra):
    return {"seed": str(seed), "banners": runs, **extra}


def test_engine_renders_the_golden_seeds_table(client, engine, catalogue):
    _compare(client, engine, _form(GOLDEN_SEED, _runs(3)))


@pytest.mark.parametrize("rows", ["1", "100", "999"])
def test_engine_renders_every_table_length(client, engine, catalogue, rows):
    _compare(client, engine, _form(RNG.getrandbits(32), _runs(2), track_length=rows))


@pytest.mark.parametrize("seed", [RNG.getrandbits(32) for _ in range(6)])
def test_engine_renders_random_seeds_and_banners(client, engine, catalogue, seed):
    _compare(client, engine, _form(seed, _runs(RNG.randint(1, 4))))


def test_engine_renders_a_simulated_guaranteed_multi(client, engine, catalogue):
    _compare(client, engine, _form(RNG.getrandbits(32), _runs(2), simulate_guaranteed="11"))


def test_engine_merges_banners_that_roll_the_same(client, engine, catalogue):
    html = _compare(client, engine, _form(RNG.getrandbits(32), [*_twins(), *_runs(1)]))
    assert html.count('<li><span class="tag">') == 2  # three banners, two legend rows


def test_engine_renders_future_ubers_and_their_targets(client, engine, catalogue):
    runs = _runs(2)
    name = runs[0].partition("|")[2]
    future = json.dumps({name: 2})
    targets = json.dumps([f"Future Uber 1 @ {name}"])
    html = _compare(
        client,
        engine,
        _form(RNG.getrandbits(32), runs, future_ubers=future, future_targets=targets),
    )
    assert "future-target" in html and "Future Uber 1" in html


def test_engine_lists_picks_and_the_wishlist_in_the_targets_panel(client, engine, catalogue):
    seed, runs = RNG.getrandbits(32), _runs(2)
    rolled = roll_selected(seed, runs, count=50)
    on_banner = next(iter(rolled.banners.values())).pulls[10].cat
    picks = [
        Cat.objects.create(name=on_banner, rarity="Rare"),
        Cat.objects.create(name="Nowhere Cat", rarity="Uber Super Rare"),
    ]
    data = _form(seed, runs, targets=[c.pk for c in picks], use_wishlist="1")
    html = _compare(client, engine, data)
    assert "find-pos" in html and "is-unreachable" in html


def test_engine_dupes_the_first_cell_on_the_remembered_last_pull(client, engine, catalogue):
    runs = _runs(3)
    for seed in (RNG.getrandbits(32) for _ in range(400)):
        first = roll_selected(seed, runs, count=1).banners
        rare = next((r.pulls[0].cat for r in first.values() if r.pulls[0].rarity == "Rare"), "")
        if rare:
            break
    _compare(client, engine, _form(seed, runs, last_cat=rare))


@pytest.mark.parametrize(
    ("idx", "guaranteed", "reroll"),
    [(14, "", ""), (31, "", ""), (8, "", "1"), (6, "1", ""), (6, "1", "1")],
)
def test_engine_lights_a_traced_cell_like_the_server(
    client, engine, catalogue, idx, guaranteed, reroll
):
    runs = _runs(3)
    data = _form(
        RNG.getrandbits(32),
        runs,
        simulate_guaranteed="11",
        trace_tag="1",
        trace_idx=str(idx),
        trace_guaranteed=guaranteed,
        trace_reroll=reroll,
    )
    assert "on-path" in _compare(client, engine, data)


def test_the_request_spells_each_name_once(client, catalogue):
    runs = _runs(3)
    request = _post(client, "/tracks/engine/", _form(GOLDEN_SEED, runs)).json()
    assert len(request["names"]) == len(set(request["names"]))
    assert {b["key"] for b in request["banners"]} == set(prepare_selected(runs))


def test_the_engine_request_needs_a_numeric_seed(client):
    assert client.post("/tracks/engine/", {"seed": "x"}).status_code == 400
