from collections.abc import Iterable, Mapping

from neko.godfat import TrackPull
from neko.graph import build_graphs
from neko.models import CATFOOD_PER_DRAW, State
from neko.search import Guaranteed, astar
from neko.subsets import SubsetPlan, solve_subsets


def plan(
    pulls_by_banner: Mapping[str, Iterable[TrackPull]],
    targets: Iterable[str],
    tickets: int,
    catfood: int,
    guaranteed_pulls: Mapping[str, Iterable[TrackPull]] | None = None,
    guaranteed: Mapping[str, Guaranteed] | None = None,
) -> list[SubsetPlan]:
    """Best plan for the wishlist. Returns the single full plan if reachable,
    else the per-subset fallback breakdown (biggest-then-cheapest).

    Pass guaranteed_pulls (the guaranteed-column outcomes per banner) and guaranteed
    (each banner's multi-roll config) to also consider guaranteed multis."""
    targets = frozenset(targets)
    start = State(0, tickets, catfood // CATFOOD_PER_DRAW, frozenset())
    graphs = build_graphs(pulls_by_banner, guaranteed_pulls)
    full = astar(graphs, targets, start, guaranteed=guaranteed)
    if full is not None:
        return [SubsetPlan(targets, full)]
    return solve_subsets(graphs, targets, start, guaranteed=guaranteed)
