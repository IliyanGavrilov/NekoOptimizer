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


def _spent(plan: Path, ticket_value: int) -> int:
    """A plan's total price in catfood-equivalent: catfood plus every ticket kind (rare,
    platinum, legend all count as ``ticket_value``), for bounds and ranking."""
    tickets = plan.tickets_used + plan.platinum_used + plan.legend_used

    return plan.cost + tickets * ticket_value


def solve_subsets(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    search: Callable[..., Path | None] = astar,
    multis: Mapping[str, Sequence[Multi]] | None = None,
    ticket_value: int = CATFOOD_PER_DRAW,
    banner_currency: Mapping[str, str] | None = None,
) -> list[SubsetPlan]:
    """Best plan for every reachable non-empty target subset, biggest first then cheapest.

    Targets that can't drop on any of these banners are thrown out up front: no subset
    that includes one can ever have a plan, but each one still DOUBLES the number of
    subsets to try (a wishlist full of them used to hang the solve completely). That
    leaves one search per subset -> 2^k searches for k reachable targets, so tell the
    caller to be careful with large k.
    """
    graphs = list(graphs)
    items = sorted(obtainable(graphs, targets))
    plans = []
    # A plan for a bigger set already collects every subset of it, so its cost is a
    # ceiling for the subset's best cost - passing it as upper_bound cuts the smaller
    # searches down hard.
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
                banner_currency=banner_currency,
                upper_bound=bound,
            )

            if plan is not None:
                bounds[wanted] = _spent(plan, ticket_value)
                plans.append(SubsetPlan(wanted, plan))

    def rank(result: SubsetPlan) -> tuple:
        # Most cats first, then least spent. `plan.cost` is catfood only (tickets are
        # free there), so ranking on it alone leaves every all-ticket plan tied at 0 and
        # ordered arbitrarily. Fold tickets into a catfood-equivalent total - the same
        # figure used for `bounds` above - so a 140-ticket plan sorts ahead of a 300-ticket
        # one; break remaining ties on catfood held (spend tickets first), then name.
        plan = result.plan
        return (
            -len(result.targets),
            _spent(plan, ticket_value),
            plan.cost,
            tuple(sorted(result.targets)),
        )

    plans.sort(key=rank)

    return plans
