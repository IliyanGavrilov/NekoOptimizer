from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations

from neko.graph import BannerGraph
from neko.models import Path, State
from neko.search import Guaranteed, astar


@dataclass(frozen=True, slots=True)
class SubsetPlan:
    targets: frozenset[str]
    plan: Path


def solve_subsets(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    search: Callable[..., Path | None] = astar,
    guaranteed: Mapping[str, Guaranteed] | None = None,
) -> list[SubsetPlan]:
    """Best plan for every reachable non-empty target subset, biggest-then-cheapest.

    One search per subset -> O(2^n) searches, so warn the caller for large n.
    """
    graphs = list(graphs)
    items = sorted(set(targets))
    plans = []
    for size in range(len(items), 0, -1):
        for combo in combinations(items, size):
            plan = search(graphs, combo, start, guaranteed=guaranteed)
            if plan is not None:
                plans.append(SubsetPlan(frozenset(combo), plan))
    plans.sort(key=lambda result: (-len(result.targets), result.plan.cost))
    return plans
