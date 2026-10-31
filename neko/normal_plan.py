# Path planning over the normal-side gacha: all machines read the same seed
# stream, so choosing WHICH machine takes the next pull steers the chain - a
# normal-ticket roll walks it forward, a lucky ticket can dupe and jump tracks.
# Budgets mirror the game's currencies: ONE pool of Normal Cat Tickets feeds the
# plain capsule and the Catfruit/Catseye event machines alike, while each Lucky
# Ticket machine burns its own. Find the pull sequence that collects the most
# target items (Dark Catseyes, above all) while keeping the most of the stashes
# the player holds dearest.

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from neko.normal import BANNERS_BY_KEY, landing, pull_once

# The machines Normal Cat Tickets feed; each lucky machine burns its own ticket.
CHEAP_KEYS = frozenset({"n", "np", "cf", "ce"})

_BEAM = 200  # states kept per depth; branching is at most the six machines
MAX_ROLLS = 500  # total pulls a plan may look ahead (keeps the search bounded)


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One pull of the plan: which machine, what it gives, and the cell it lands
    on (``dupe`` marks a reroll - the branch value, jumping tracks; ``forced`` one
    only this machine deals, where the machine before it would roll on)."""

    machine: str
    item: str
    position: int
    track: str
    dupe: bool
    target: bool
    forced: bool = False


@dataclass(frozen=True, slots=True)
class NormalPlan:
    """The best pull sequence found. ``hits`` counts target items collected;
    ``spent`` is rolls used per machine; ``seed_after``/``last_item`` are the
    state after the final step (feed them back in to continue). The sequence is
    trimmed at its last target - pulls past it would only waste rolls."""

    steps: tuple[PlanStep, ...]
    hits: int
    spent: Mapping[str, int]
    seed_after: int
    last_item: str


@dataclass(frozen=True, slots=True)
class _Node:
    """One beam state: the chain so far. ``budgets`` counts what remains of each
    budget GROUP (machines sharing a currency share an entry), dearest first."""

    seed: int
    position: int
    track: str
    last: str
    budgets: tuple[int, ...]
    hits: int = 0
    forced: int = 0
    steps: tuple[PlanStep, ...] = ()

    def rank(self) -> tuple:
        """More hits first, then the fewest forced track changes (the longest runs on
        one machine), then the most left of each budget in turn, then the fewest
        rolls."""
        return (
            -self.hits,
            self.forced,
            tuple(-count for count in self.budgets),
            len(self.steps),
        )


def plan_normal(
    seed: int,
    budgets: Sequence[tuple[int, Sequence[str]]],
    targets: frozenset[str],
    last_item: str = "",
    beam: int = _BEAM,
) -> NormalPlan:
    """The pull sequence from ``seed`` that collects the most items in ``targets``.
    ``budgets`` are the player's currencies: (rolls, machines that currency feeds)
    pairs - normal tickets list every ticket machine that's live, each lucky
    ticket kind lists its own - dearest first. Beam search over the shared stream,
    one machine choice per pull. Ties force the fewest track changes, so the plan
    stays in long runs you can roll ten at a time; then they keep the most of the
    first budget, then the next, then take the fewest rolls, so the walking pulls
    between targets come out of the stash the player can best spare."""
    groups = [
        (min(count, MAX_ROLLS), [key for key in keys if key in BANNERS_BY_KEY])
        for count, keys in budgets
        if count > 0
    ]
    groups = [(count, keys) for count, keys in groups if keys]
    if not groups or not targets:
        return NormalPlan((), 0, {}, seed, last_item)

    choices = [(index, key) for index, (_, keys) in enumerate(groups) for key in keys]
    start_budgets = tuple(count for count, _ in groups)
    depth = min(sum(start_budgets), MAX_ROLLS)
    start = _Node(seed, 1, "A", last_item, start_budgets)
    best = start  # the empty plan: rolling nothing is legal

    nodes = [start]
    for _ in range(depth):
        grown: dict[tuple, _Node] = {}
        for node in nodes:
            for index, key in choices:
                if node.budgets[index] == 0:
                    continue

                item, after, extra = pull_once(node.seed, BANNERS_BY_KEY[key], node.last)
                dupe = extra > 0
                hit = item in targets
                previous = node.steps[-1].machine if node.steps else key
                forced = (
                    dupe
                    and previous != key
                    and not pull_once(node.seed, BANNERS_BY_KEY[previous], node.last)[2]
                )
                step = PlanStep(key, item, node.position, node.track, dupe, hit, forced)
                if dupe:
                    position, track = landing(node.position, node.track, extra)
                else:
                    position, track = node.position + 1, node.track

                spent = tuple(count - (i == index) for i, count in enumerate(node.budgets))
                child = _Node(
                    after,
                    position,
                    track,
                    item,
                    spent,
                    node.hits + hit,
                    node.forced + forced,
                    node.steps + (step,),
                )
                if hit and child.rank() < best.rank():
                    best = child

                # The machine you're on joins the state: it decides which dupes are forced.
                state = (child.seed, child.last, child.budgets, key)
                seen = grown.get(state)
                if seen is None or child.rank() < seen.rank():
                    grown[state] = child

        nodes = sorted(grown.values(), key=_Node.rank)[:beam]
        if not nodes:
            break

    spent: dict[str, int] = {}
    for step in best.steps:
        spent[step.machine] = spent.get(step.machine, 0) + 1

    return NormalPlan(
        best.steps,
        best.hits,
        spent,
        best.seed if best.steps else seed,
        best.last if best.steps else last_item,
    )
