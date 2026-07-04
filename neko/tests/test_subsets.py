import time

from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Rarity, State, TrackPull
from neko.subsets import solve_subsets

U = Rarity.UBER_SUPER_RARE


def banner():
    return BannerGraph(
        "x", [TrackPull(1, "A", "Aaa", U), TrackPull(2, "A", "Bbb", U), TrackPull(3, "A", "Ccc", U)]
    )


def start(tickets=0, catfood=0):
    return State(0, tickets, catfood, frozenset())


def test_biggest_subset_ranked_first():
    plans = solve_subsets([banner()], {"Aaa", "Bbb", "Ccc"}, start(tickets=3))
    assert plans[0].targets == frozenset({"Aaa", "Bbb", "Ccc"})


def test_returns_every_non_empty_subset():
    plans = solve_subsets([banner()], {"Aaa", "Bbb", "Ccc"}, start(tickets=3))
    assert len(plans) == 7


def test_singletons_ordered_by_cost():
    plans = solve_subsets([banner()], {"Aaa", "Bbb", "Ccc"}, start(catfood=10))
    costs = [p.plan.cost for p in plans if len(p.targets) == 1]
    assert costs == [CATFOOD_PER_DRAW, 2 * CATFOOD_PER_DRAW, 3 * CATFOOD_PER_DRAW]


def test_drops_subsets_that_are_unaffordable():
    plans = solve_subsets([banner()], {"Aaa", "Bbb"}, start(catfood=1))
    assert [p.targets for p in plans] == [frozenset({"Aaa"})]


def test_unobtainable_targets_do_not_multiply_the_subsets():
    # A wishlist-sized target set where most cats occur in no banner: each absent cat
    # used to DOUBLE the enumeration (2^100 subsets - the search never returned).
    noise = {f"wish{i:03d}" for i in range(100)}
    begin = time.perf_counter()
    plans = solve_subsets([banner()], {"Aaa", "Bbb", "Ccc"} | noise, start(tickets=3))
    assert time.perf_counter() - begin < 5
    assert len(plans) == 7  # same subsets as without the noise
    assert plans[0].targets == frozenset({"Aaa", "Bbb", "Ccc"})
