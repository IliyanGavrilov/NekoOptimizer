from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Path, State
from neko.search import Multi, astar


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
    prefer: str = "tickets",
    banner_limits: Mapping[str, int] | None = None,
) -> list[SubsetPlan]:
    """Best plan for every reachable non-empty target subset, biggest-then-cheapest.

    One search per subset -> O(2^n) searches, so warn the caller for large n.
    """
    graphs = list(graphs)
    items = sorted(set(targets))
    plans = []
    for size in range(len(items), 0, -1):
        for combo in combinations(items, size):
            plan = search(
                graphs,
                combo,
                start,
                multis=multis,
                ticket_value=ticket_value,
                prefer=prefer,
                banner_limits=banner_limits,
            )
            if plan is not None:
                plans.append(SubsetPlan(frozenset(combo), plan))
    plans.sort(key=lambda result: (-len(result.targets), result.plan.cost))
    return plans
