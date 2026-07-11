# The normal-side path planner: whatever sequence it claims must replay exactly
# on the real machines, respect its budgets, and never trail pulls past its last
# target - and choosing between machines can only ever help.

import pytest

from neko.normal import BANNERS_BY_KEY, landing, play, pull_once
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
    [{"ce": 30}, {"np": 40, "ce": 10}, {"np": 25, "lt": 8, "ce": 8}],
)
def test_plan_replays_on_the_real_machines(budgets):
    plan = plan_normal(SEED, budgets, DARK)

    dealt, end = replay(SEED, plan.steps)
    assert dealt == [step.item for step in plan.steps]
    assert end == plan.seed_after if plan.steps else plan.seed_after == SEED
    assert plan.hits == sum(item in DARK for item in dealt)
    for key, rolls in plan.spent.items():
        assert rolls <= budgets[key]


def test_plan_stops_at_its_last_target():
    plan = plan_normal(SEED, {"ce": 30}, DARK)

    assert plan.steps  # the 15B dark is reachable within 30 catseye rolls
    assert plan.steps[-1].target
    assert plan.steps[-1].item == "Dark Catseye"


def test_single_machine_plan_is_the_forced_chain():
    """With one machine budgeted there's nothing to choose: the plan must be the
    linear play chain, trimmed at its last dark."""
    count = 30
    items, _ = play(SEED, BANNERS_BY_KEY["ce"], count)
    darks = [i for i, item in enumerate(items) if item == "Dark Catseye"]

    plan = plan_normal(SEED, {"ce": count}, DARK)

    assert plan.hits == len(darks)
    assert [step.item for step in plan.steps] == items[: darks[-1] + 1]


def test_a_second_machine_never_hurts():
    baseline = plan_normal(SEED, {"ce": 12}, DARK)
    steered = plan_normal(SEED, {"np": 30, "ce": 12}, DARK)

    assert steered.hits >= baseline.hits
    # And the tickets it does spend never exceed the ce budget.
    assert steered.spent.get("ce", 0) <= 12


def test_plan_chases_other_targets():
    """The same search chases any item set - upgrades here (rare-ticket fodder)."""
    from neko.normal import UPGRADES

    count = 25
    items, _ = play(SEED, BANNERS_BY_KEY["np"], count)
    expected = sum(item in UPGRADES for item in items)

    plan = plan_normal(SEED, {"np": count}, frozenset(UPGRADES))

    assert plan.hits == expected


def test_plan_handles_nothing_to_do():
    assert plan_normal(SEED, {}, DARK).hits == 0
    assert plan_normal(SEED, {"ce": 10}, frozenset()).hits == 0
    empty = plan_normal(SEED, {"nope": 5}, DARK)
    assert empty.steps == ()
    assert empty.seed_after == SEED
