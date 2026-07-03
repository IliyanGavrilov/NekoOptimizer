from collections.abc import Iterable, Mapping, Sequence

from neko.graph import build_graphs
from neko.models import CATFOOD_PER_DRAW, State, TrackPull
from neko.search import Multi, astar
from neko.subsets import SubsetPlan, solve_subsets


def plan(
    pulls_by_banner: Mapping[str, Iterable[TrackPull]],
    targets: Iterable[str],
    tickets: int,
    catfood: int,
    guaranteed_pulls: Mapping[str, Iterable[TrackPull]] | None = None,
    multis: Mapping[str, Sequence[Multi]] | None = None,
    ticket_value: int = CATFOOD_PER_DRAW,
    banner_limits: Mapping[str, int] | None = None,
    rerolls: Mapping[str, Iterable[TrackPull]] | None = None,
) -> list[SubsetPlan]:
    """Best plan for the wishlist. Returns the single full plan if reachable,
    else the per-subset fallback breakdown (biggest-then-cheapest).

    Pass guaranteed_pulls (the guaranteed-column outcomes per banner) and multis
    (each banner's multi-roll options) to also consider multi-rolls. ticket_value
    prices a rare ticket in catfood (tickets are spent first unless dearer)."""
    targets = frozenset(targets)
    start = State(0, tickets, catfood // CATFOOD_PER_DRAW, frozenset())
    graphs = build_graphs(pulls_by_banner, guaranteed_pulls, rerolls)
    full = astar(
        graphs,
        targets,
        start,
        multis=multis,
        ticket_value=ticket_value,
        banner_limits=banner_limits,
    )
    if full is not None:
        return [SubsetPlan(targets, full)]
    return solve_subsets(
        graphs,
        targets,
        start,
        multis=multis,
        ticket_value=ticket_value,
        banner_limits=banner_limits,
    )
