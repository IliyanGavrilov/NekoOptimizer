import heapq
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import count

from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Leg, Path, Pull, State

INF = float("inf")


@dataclass(frozen=True, slots=True)
class Multi:
    """A multi-roll option: `rolls` pulls for `cost` catfood; if `guaranteed`, the last is uber."""

    rolls: int
    cost: int
    guaranteed: bool = True


def _occurrences(graphs: Iterable[BannerGraph], targets: frozenset[str]) -> dict[str, list[int]]:
    spots: dict[str, list[int]] = {target: [] for target in targets}
    for graph in graphs:
        for position in graph.positions():
            outcome = graph.outcome(position)
            if not outcome.switched and outcome.cat in targets:
                spots[outcome.cat].append(position)
    for positions in spots.values():
        positions.sort()
    return spots


def _heuristic(
    position: int, tickets_left: int, remaining: frozenset[str], occurrences: dict[str, list[int]]
) -> float:
    # Lower-bound the pulls to the farthest still-needed target: each pull advances the
    # position by at most 3, so reaching a target d away costs at least d // 3 + 1 pulls.
    worst = 0
    for cat in remaining:
        spots = occurrences[cat]
        index = bisect_left(spots, position)
        if index == len(spots):
            return INF
        worst = max(worst, (spots[index] - position) // 3 + 1)
    return max(0, worst - tickets_left) * CATFOOD_PER_DRAW


def _node_h(state: State, targets: frozenset[str], occurrences, multis) -> float:
    # Multis bundle many cats per fixed cost, undercutting the single-roll bound,
    # so fall back to uniform-cost (0) when any are available.
    if multis:
        return 0.0
    return _heuristic(state.position, state.tickets_left, targets - state.found, occurrences)


def _reconstruct(goal: State, came_from: dict, start: State) -> Path:
    legs: list[Leg] = []
    state = goal
    while state in came_from:
        previous, leg = came_from[state]
        legs.append(leg)
        state = previous
    legs.reverse()
    pulls = tuple(pull for leg in legs for pull in leg.pulls)
    return Path(
        pulls,
        start.tickets_left - goal.tickets_left,
        start.catfood_draws - goal.catfood_draws,
        tuple(legs),
    )


def _pull(state: State, graph: BannerGraph, targets: frozenset[str]):
    # The single legal move of pulling `graph` at `state`, or None if out of data/resources.
    outcome = graph.outcome(state.position)
    if outcome is None:
        return None
    if state.tickets_left > 0:
        tickets, catfood, step = state.tickets_left - 1, state.catfood_draws, 0
    elif state.catfood_draws > 0:
        tickets, catfood, step = 0, state.catfood_draws - 1, CATFOOD_PER_DRAW
    else:
        return None
    found = state.found
    if not outcome.switched and outcome.cat in targets:
        found = found | {outcome.cat}
    nxt = State(outcome.next_position, tickets, catfood, found, graph.banner_id)
    pull = Pull(state.position, graph.banner_id, outcome.cat, outcome.rarity)
    return nxt, Leg(graph.banner_id, "Single pull", step, (pull,))


def _multi_move(state: State, graph: BannerGraph, multi: Multi, targets: frozenset[str]):
    # `rolls` normal pulls (the last replaced by the guaranteed uber if guaranteed),
    # for a fixed catfood cost.
    draws = multi.cost // CATFOOD_PER_DRAW
    if state.catfood_draws < draws:
        return None
    position = state.position
    found = state.found
    pulls = []
    normal_rolls = multi.rolls - 1 if multi.guaranteed else multi.rolls
    for _ in range(normal_rolls):
        outcome = graph.outcome(position)
        if outcome is None:
            return None
        pulls.append(Pull(position, graph.banner_id, outcome.cat, outcome.rarity))
        if not outcome.switched and outcome.cat in targets:
            found = found | {outcome.cat}
        position = outcome.next_position
    if multi.guaranteed:
        final = graph.guaranteed(position)
        if final is None:
            return None
        pulls.append(Pull(position, graph.banner_id, final.cat, final.rarity))
        if final.cat in targets:
            found = found | {final.cat}
        position = final.next_position
    nxt = State(position, state.tickets_left, state.catfood_draws - draws, found, graph.banner_id)
    kind = f"{multi.rolls}-roll" + (" (guaranteed)" if multi.guaranteed else "")
    return nxt, Leg(graph.banner_id, kind, multi.cost, tuple(pulls))


def _switch(state: State, leg: Leg) -> int:
    # 1 if this leg rolls a different banner than the previous pull (the first pull is free).
    return 1 if state.last_banner and state.last_banner != leg.banner_id else 0


def _candidate_moves(state, graph, targets, multis):
    single = _pull(state, graph, targets)
    if single is not None:
        yield single
    for multi in multis.get(graph.banner_id, ()) if multis else ():
        move = _multi_move(state, graph, multi, targets)
        if move is not None:
            yield move


def astar(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    upper_bound: float = INF,
    multis: Mapping[str, Sequence[Multi]] | None = None,
) -> Path | None:
    """Cheapest pull plan collecting all targets, or None. A* over states.

    Pass upper_bound (e.g. a beam-search cost) to prune branches that cannot beat it.
    Pass multis to also consider each banner's multi-roll options.
    """
    graphs = list(graphs)
    targets = frozenset(targets)
    occurrences = _occurrences(graphs, targets)
    # Lexicographic cost (catfood, switches): cheapest first, fewest banner switches breaks ties.
    g_score: dict[State, tuple[int, int]] = {start: (0, 0)}
    came_from: dict[State, tuple] = {}
    counter = count()
    heap = [(_node_h(start, targets, occurrences, multis), 0, next(counter), 0, 0, start)]
    while heap:
        _, _, _, cost, switches, state = heapq.heappop(heap)
        if (cost, switches) > g_score[state]:
            continue
        if targets <= state.found:
            return _reconstruct(state, came_from, start)
        for graph in graphs:
            for nxt, leg in _candidate_moves(state, graph, targets, multis):
                new_cost = cost + leg.cost
                new_switches = switches + _switch(state, leg)
                if (new_cost, new_switches) < g_score.get(nxt, (INF, INF)):
                    h = _node_h(nxt, targets, occurrences, multis)
                    if h == INF or new_cost + h > upper_bound:
                        continue
                    g_score[nxt] = (new_cost, new_switches)
                    came_from[nxt] = (state, leg)
                    entry = (new_cost + h, new_switches, next(counter), new_cost, new_switches, nxt)
                    heapq.heappush(heap, entry)
    return None


def beam_search(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    width: int,
    multis: Mapping[str, Sequence[Multi]] | None = None,
) -> Path | None:
    """Keep only the `width` most promising paths each step. Fast, not guaranteed optimal."""
    graphs = list(graphs)
    targets = frozenset(targets)
    if targets <= start.found:
        return _reconstruct(start, {}, start)
    occurrences = _occurrences(graphs, targets)
    # Lexicographic cost (catfood, switches): cheapest first, fewest banner switches breaks ties.
    best_cost: dict[State, tuple[int, int]] = {start: (0, 0)}
    came_from: dict[State, tuple] = {}
    best_goal: State | None = None
    best_goal_cost = (INF, INF)
    frontier = [start]
    while frontier:
        ranked: list[tuple[float, int, State]] = []
        for state in frontier:
            cost, switches = best_cost[state]
            for graph in graphs:
                for nxt, leg in _candidate_moves(state, graph, targets, multis):
                    new_cost = cost + leg.cost
                    new_switches = switches + _switch(state, leg)
                    if (new_cost, new_switches) >= best_cost.get(nxt, (INF, INF)):
                        continue
                    best_cost[nxt] = (new_cost, new_switches)
                    came_from[nxt] = (state, leg)
                    if targets <= nxt.found:
                        if (new_cost, new_switches) < best_goal_cost:
                            best_goal, best_goal_cost = nxt, (new_cost, new_switches)
                        continue
                    h = _node_h(nxt, targets, occurrences, multis)
                    if h == INF:
                        continue
                    ranked.append((new_cost + h, new_switches, nxt))
        ranked.sort(key=lambda item: (item[0], item[1]))
        frontier = [state for _, _, state in ranked[:width]]
    return _reconstruct(best_goal, came_from, start) if best_goal is not None else None
