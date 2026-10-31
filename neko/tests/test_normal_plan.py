# The normal-side path planner: whatever sequence it claims must replay exactly
# on the real machines, respect its budgets, and never trail pulls past its last
# target - and choosing between machines can only ever help.

from itertools import product

import pytest

from neko.normal import BANNERS_BY_KEY, UPGRADES, landing, play, pull_once
from neko.normal_plan import plan_normal

SEED = 2157514271  # the ce grid shows a Dark Catseye at 15B for this seed
DARK = frozenset({"Dark Catseye"})


def replay(seed, steps, last_item=""):
    """Walk a plan's steps through pull_once and return what the machines deal."""
    position, track, prev = 1, "A", last_item
    dealt = []
    for step in steps:
        assert (step.position, step.track) == (position, track)
        item, seed, extra = pull_once(seed, BANNERS_BY_KEY[step.machine], prev)
        dealt.append(item)
        assert step.dupe == (extra > 0)
        if extra:
            position, track = landing(position, track, extra)
        else:
            position += 1

        prev = item

    return dealt, seed


@pytest.mark.parametrize(
    "budgets",
    [
        [(30, ("ce",))],
        [(50, ("np", "ce"))],  # one normal-ticket pool feeding both machines
        [(30, ("np", "ce")), (8, ("lt",))],
    ],
)
def test_plan_replays_on_the_real_machines(budgets):
    plan = plan_normal(SEED, budgets, DARK)

    dealt, end = replay(SEED, plan.steps)
    assert dealt == [step.item for step in plan.steps]
    assert end == plan.seed_after if plan.steps else plan.seed_after == SEED
    assert plan.hits == sum(item in DARK for item in dealt)
    for count, keys in budgets:
        assert sum(plan.spent.get(key, 0) for key in keys) <= count


def test_plan_stops_at_its_last_target():
    plan = plan_normal(SEED, [(30, ("ce",))], DARK)

    assert plan.steps  # the 15B dark is reachable within 30 catseye rolls
    assert plan.steps[-1].target
    assert plan.steps[-1].item == "Dark Catseye"


def test_single_machine_plan_is_the_forced_chain():
    """With one machine budgeted there's nothing to choose: the plan must be the
    linear play chain, trimmed at its last dark."""
    count = 30
    items, _ = play(SEED, BANNERS_BY_KEY["ce"], count)
    darks = [i for i, item in enumerate(items) if item == "Dark Catseye"]

    plan = plan_normal(SEED, [(count, ("ce",))], DARK)

    assert plan.hits == len(darks)
    assert [step.item for step in plan.steps] == items[: darks[-1] + 1]


def test_a_second_machine_never_hurts():
    """More rolls in the shared normal-ticket pool, with the walking machine in it,
    can only help - and the same pool feeds both, exactly like the game."""
    baseline = plan_normal(SEED, [(12, ("ce",))], DARK)
    steered = plan_normal(SEED, [(42, ("np", "ce"))], DARK)

    assert steered.hits >= baseline.hits
    assert sum(steered.spent.values()) <= 42


def test_walking_pulls_spare_the_dearest_budget():
    """Budgets come dearest first: the plan collects the same darks either way, but
    the pulls that only walk the track come out of the stash listed later."""
    catseye, lucky = (30, ("ce",)), (30, ("lt",))
    keep_normal = plan_normal(SEED, [catseye, lucky], DARK)
    keep_lucky = plan_normal(SEED, [lucky, catseye], DARK)

    assert keep_normal.hits == keep_lucky.hits > 0
    assert keep_normal.spent["ce"] < keep_lucky.spent["ce"]
    assert keep_normal.spent["lt"] > keep_lucky.spent["lt"]


def _best_by_brute_force(seed, budgets, targets):
    """The best rank over every machine sequence the budgets allow, ending on a target:
    most hits, then fewest forced track changes, then most of each budget left, then
    fewest pulls."""
    machines = [key for _, keys in budgets for key in keys]
    best = None
    for length in range(1, sum(count for count, _ in budgets) + 1):
        for sequence in product(machines, repeat=length):
            left = [count - sum(key in keys for key in sequence) for count, keys in budgets]
            if min(left) < 0:
                continue

            state, last, previous, hits, forced = seed, "", None, 0, 0
            for key in sequence:
                item, after, extra = pull_once(state, BANNERS_BY_KEY[key], last)
                if extra and previous not in (None, key):
                    forced += not pull_once(state, BANNERS_BY_KEY[previous], last)[2]
                hits += item in targets
                state, last, previous = after, item, key
            if item in targets:
                rank = (-hits, forced, tuple(-n for n in left), length)
                best = rank if best is None else min(best, rank)

    return best


@pytest.mark.parametrize("seed", range(1, 41))
def test_small_plans_are_the_exact_optimum(seed):
    """On budgets small enough to try every sequence, the beam finds the best one: no
    forced track change it could avoid, and the walking pulls on the spare stash."""
    budgets = [(4, ("ce",)), (4, ("lt",))]
    targets = frozenset({"10K XP", "Speed Up"})

    plan = plan_normal(seed, budgets, targets)

    left = tuple(-(count - sum(plan.spent.get(key, 0) for key in keys)) for count, keys in budgets)
    forced = sum(step.forced for step in plan.steps)
    assert (-plan.hits, forced, left, len(plan.steps)) == _best_by_brute_force(
        seed, budgets, targets
    )


def test_plan_chases_other_targets():
    """The same search chases any item set - upgrades here (rare-ticket fodder)."""
    count = 25
    items, _ = play(SEED, BANNERS_BY_KEY["np"], count)
    expected = sum(item in UPGRADES for item in items)

    plan = plan_normal(SEED, [(count, ("np",))], frozenset(UPGRADES))

    assert plan.hits == expected


def test_plan_handles_nothing_to_do():
    assert plan_normal(SEED, [], DARK).hits == 0
    assert plan_normal(SEED, [(10, ("ce",))], frozenset()).hits == 0
    empty = plan_normal(SEED, [(5, ("nope",))], DARK)
    assert empty.steps == ()
    assert empty.seed_after == SEED
