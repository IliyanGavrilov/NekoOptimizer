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
    banner_currency: Mapping[str, str] | None = None,
    platinum: int = 0,
    legend: int = 0,
    rerolls: Mapping[str, Iterable[TrackPull]] | None = None,
    guaranteed_rerolls: Mapping[str, Iterable[TrackPull]] | None = None,
) -> list[SubsetPlan]:
    """Best plan for the wishlist. Returns the one full plan if it's reachable, else
    the per-subset breakdown to fall back on (biggest first, then cheapest).

    Pass guaranteed_pulls (each banner's guaranteed-column results) and multis (each
    banner's multi-roll options) to let it use multi-rolls too. ticket_value is what a
    rare ticket is worth in catfood (tickets get spent first unless they're pricier).
    banner_currency ({banner: "platinum"/"legend"}) marks the capsule banners funded from
    their own ``platinum``/``legend`` ticket pools."""
    targets = frozenset(targets)
    start = State(
        0,
        tickets,
        catfood // CATFOOD_PER_DRAW,
        frozenset(),
        platinum_left=platinum,
        legend_left=legend,
    )
    graphs = build_graphs(pulls_by_banner, guaranteed_pulls, rerolls, guaranteed_rerolls)
    full = astar(
        graphs,
        targets,
        start,
        multis=multis,
        ticket_value=ticket_value,
        banner_currency=banner_currency,
    )

    if full is not None:
        return [SubsetPlan(targets, full)]

    return solve_subsets(
        graphs,
        targets,
        start,
        multis=multis,
        ticket_value=ticket_value,
        banner_currency=banner_currency,
    )
