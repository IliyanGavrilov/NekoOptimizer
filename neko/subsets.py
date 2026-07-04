from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Path, State
from neko.search import Multi, astar, obtainable


@dataclass(frozen=True, slots=True)
class SubsetPlan:
    targets: frozenset[str]
    plan: Path


def solve_subsets(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    search: Callable[..., Path | None] = astar,
    multis: Mapping[str, Sequence[Multi]] | None = None,
    ticket_value: int = CATFOOD_PER_DRAW,
    banner_limits: Mapping[str, int] | None = None,
) -> list[SubsetPlan]:
    """Best plan for every reachable non-empty target subset, biggest-then-cheapest.

    Targets that occur nowhere in the graphs are dropped up front: no subset holding
    one can ever have a plan, yet each would DOUBLE the enumeration (a wishlist of
    them used to hang the solve outright). One search per remaining subset ->
    O(2^k) searches in the k obtainable targets, so warn the caller for large k.
    """
    graphs = list(graphs)
    items = sorted(obtainable(graphs, targets))
    plans = []
    # A superset's plan also collects every subset, so its cost bounds the subset's
    # optimum - passing it as upper_bound prunes the smaller searches hard.
    bounds: dict[frozenset[str], float] = {}
    for size in range(len(items), 0, -1):
        for combo in combinations(items, size):
            wanted = frozenset(combo)
            bound = min(
                (cost for key, cost in bounds.items() if wanted <= key), default=float("inf")
            )
            plan = search(
                graphs,
                combo,
                start,
                multis=multis,
                ticket_value=ticket_value,
                banner_limits=banner_limits,
                upper_bound=bound,
            )
            if plan is not None:
                bounds[wanted] = plan.cost + plan.tickets_used * ticket_value
                plans.append(SubsetPlan(wanted, plan))
    plans.sort(key=lambda result: (-len(result.targets), result.plan.cost))
    return plans
