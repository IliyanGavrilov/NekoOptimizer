import json
import random

import pytest

from neko.gachadata import load_events
from neko.roller import prepare_selected, roll_selected
from neko.tests.test_seek import GOLDEN_SEED
from planner.models import Cat
from planner.test_tracks_engine import _same, _twins, catalogue  # noqa: F401

# The reference plan views are routed only for tests (planner.reference_urls).
pytestmark = [pytest.mark.django_db, pytest.mark.urls("planner.reference_urls")]

RNG = random.Random(20261017)  # nosec B311
EVENTS = load_events()


def _runs(count, keep=lambda e: True):
    events = [e for e in EVENTS if keep(e)]
    return [f"{e.start}|{e.name}" for e in RNG.sample(events, count)]


def _guaranteed_runs(count):
    """Runs with a guaranteed multi on offer, so plans can use one."""
    runs = []
    while len(runs) < count:
        run = _runs(1, lambda e: e.guaranteed)[0]
        prepared = prepare_selected([run])
        if any(p.multis for p in prepared.values()):
            runs.append(run)
    return runs


def _capsules():
    """The Platinum and Legend Capsules runs live alongside one regular banner."""
    for e in RNG.sample(EVENTS, len(EVENTS)):
        live = [x for x in EVENTS if x.start <= e.start <= x.end]
        plat = next((x for x in live if "platinum capsules" in x.name.lower()), None)
        leg = next((x for x in live if "legend capsules" in x.name.lower()), None)
        if plat and leg and "capsules" not in e.name.lower():
            return [f"{x.start}|{x.name}" for x in (e, plat, leg)]
    raise AssertionError("no live capsule pair")


def _targets(seed, runs, count, rarity=None, rows=100):
    """Cats that really roll within ``rows`` on these banners, as picker Cats."""
    rolled = roll_selected(seed, runs, count=rows)
    names = []
    for rolls in rolled.banners.values():
        for p in rolls.pulls + rolls.guaranteed:
            if p.cat and p.cat not in names and (rarity is None or p.rarity == rarity):
                names.append(p.cat)
    picked = RNG.sample(names, min(count, len(names)))
    return [Cat.objects.create(name=name, rarity="Uber Super Rare").pk for name in picked]


def _form(seed, runs, targets, **extra):
    data = {
        "seed": str(seed),
        "banners": runs,
        "targets": targets,
        "tickets": "20",
        "catfood": "4500",
        "ticket_value": "150",
        "platinum_cap": "1",
        "legend_cap": "1",
        "horizon": "300",
    }
    return {**data, **extra}


def _compare(client, engine, data, row=None):
    path = "/reference/plan/row/" if row else "/plan/row/"
    if row:
        data = {**data, "subset": row}
        expected = client.post("/reference/plan/row/", data).content.decode()
        request = client.post("/plan/row/", data).json()
    else:
        expected = client.post("/reference/plan/", data).json()["solutions_html"]
        request = client.post("/plan/", data).json()
    got = engine(request)
    expected, actual = _same(expected), _same(got)
    if expected == actual:
        return expected
    at = next(
        (i for i, (a, b) in enumerate(zip(expected, actual, strict=False)) if a != b),
        min(len(expected), len(actual)),
    )
    around = slice(max(at - 200, 0), at + 200)
    pytest.fail(
        f"{path} differs at {at}:\n  django: {expected[around]}\n  engine: {actual[around]}"
    )


def test_plans_match_on_a_budget(client, engine, catalogue):  # noqa: F811
    seed, runs = GOLDEN_SEED, _runs(3)
    html = _compare(client, engine, _form(seed, runs, _targets(seed, runs, 3)))
    assert "apply-plan" in html


@pytest.mark.parametrize("seed", [RNG.getrandbits(32) for _ in range(5)])
def test_plans_match_on_random_banners_and_targets(client, engine, catalogue, seed):  # noqa: F811
    runs = _runs(RNG.randint(1, 3))
    _compare(client, engine, _form(seed, runs, _targets(seed, runs, RNG.randint(1, 4))))


def test_plans_match_in_explore_mode(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), _runs(2)
    data = _form(seed, runs, _targets(seed, runs, 3, rows=300), explore="on")
    _compare(client, engine, data)


def test_plans_match_with_guaranteed_multis(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), _guaranteed_runs(2)
    targets = _targets(seed, runs, 3, rarity="Uber Super Rare")
    html = _compare(client, engine, _form(seed, runs, targets, catfood="30000"))
    assert "(guaranteed)" in html or "guaranteed-col" in html


def test_plans_match_on_the_capsules_own_tickets(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), _capsules()
    targets = _targets(seed, runs, 3)
    html = _compare(client, engine, _form(seed, runs, targets, platinum_cap="2", legend_cap="1"))
    assert "capsule-tag" in html


def test_plans_match_when_a_ticket_is_worth_more_than_a_draw(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), _runs(2)
    _compare(client, engine, _form(seed, runs, _targets(seed, runs, 2), ticket_value="400"))


def test_plans_match_for_a_big_wishlist(client, engine, catalogue):  # noqa: F811
    # More than SUBSET_TARGET_LIMIT obtainable cats: the bounded beam search plus per-cat rows.
    picker = random.Random(7)  # nosec B311
    seed, runs = GOLDEN_SEED, [f"{e.start}|{e.name}" for e in picker.sample(EVENTS, 2)]
    first = next(iter(roll_selected(seed, runs, count=40).banners.values()))
    wanted = list(dict.fromkeys(p.cat for p in first.pulls if p.cat))[:14]
    catalogue.owned.clear()
    catalogue.wanted.set(catalogue.wanted.model.objects.filter(name__in=wanted))
    data = _form(seed, runs, [], use_wishlist="on", tickets="60", catfood="60000")
    assert "best found" in _compare(client, engine, data)


def test_plans_match_with_an_unreachable_pick(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), _runs(2)
    targets = [*_targets(seed, runs, 2), Cat.objects.create(name="Nowhere Cat").pk]
    _compare(client, engine, _form(seed, runs, targets))


def test_plans_match_with_future_ubers(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), _runs(2)
    name = runs[0].partition("|")[2]
    data = _form(
        seed,
        runs,
        _targets(seed, runs, 1),
        future_ubers=json.dumps({name: 2}),
        future_targets=json.dumps([f"Future Uber 1 @ {name}"]),
    )
    _compare(client, engine, data)


def test_plans_match_from_a_remembered_last_pull(client, engine, catalogue):  # noqa: F811
    runs = _runs(2)
    for seed in (RNG.getrandbits(32) for _ in range(400)):
        first = roll_selected(seed, runs, count=1).banners
        rare = next((r.pulls[0].cat for r in first.values() if r.pulls[0].rarity == "Rare"), "")
        if rare:
            break
    _compare(client, engine, _form(seed, runs, _targets(seed, runs, 2), last_cat=rare))


def test_plans_match_across_banners_that_roll_the_same(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), [*_twins(), *_runs(1)]
    _compare(client, engine, _form(seed, runs, _targets(seed, runs, 3)))


def test_an_opened_row_matches(client, engine, catalogue):  # noqa: F811
    seed, runs = RNG.getrandbits(32), _runs(2)
    targets = _targets(seed, runs, 3)
    names = list(Cat.objects.filter(pk__in=targets).values_list("name", flat=True))
    _compare(client, engine, _form(seed, runs, targets), row=names[:2])


def test_the_plan_request_carries_the_budget_and_scoped_targets(client, catalogue):  # noqa: F811
    seed, runs = GOLDEN_SEED, _runs(2)
    targets = [*_targets(seed, runs, 2), Cat.objects.create(name="Nowhere Cat").pk]
    request = client.post("/plan/", _form(seed, runs, targets)).json()
    names = {request["names"][i] for i in request["plan"]["targets"]}
    assert "Nowhere Cat" not in names and len(names) == 2
    assert (request["plan"]["tickets"], request["plan"]["catfood"]) == (20, 4500)
