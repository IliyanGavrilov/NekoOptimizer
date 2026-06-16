from collections.abc import Iterable, Mapping

from neko.godfat import TrackPull
from neko.graph import build_graphs
from neko.models import CATFOOD_PER_DRAW, State
from neko.search import astar
from neko.subsets import SubsetPlan, solve_subsets


def plan(
    pulls_by_banner: Mapping[str, Iterable[TrackPull]],
    targets: Iterable[str],
    tickets: int,
    catfood: int,
) -> list[SubsetPlan]:
    """Best plan for the wishlist. Returns the single full plan if reachable,
    else the per-subset fallback breakdown (biggest-then-cheapest)."""
    targets = frozenset(targets)
    start = State(0, tickets, catfood // CATFOOD_PER_DRAW, frozenset())
    graphs = build_graphs(pulls_by_banner)
    full = astar(graphs, targets, start)
    if full is not None:
        return [SubsetPlan(targets, full)]
    return solve_subsets(graphs, targets, start)
