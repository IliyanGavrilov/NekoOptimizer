import heapq
from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import count

from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Path, Pull, State

INF = float("inf")


@dataclass(frozen=True, slots=True)
class Guaranteed:
    """A banner's guaranteed multi-roll: `rolls` pulls (last = uber) for `cost` catfood."""

    rolls: int
    cost: int


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


def _node_h(state: State, targets: frozenset[str], occurrences, guaranteed) -> float:
    # Guaranteed multis bundle many cats per fixed cost, undercutting the single-roll
    # bound, so fall back to uniform-cost (0) when they're available.
    if guaranteed:
        return 0.0
    return _heuristic(state.position, state.tickets_left, targets - state.found, occurrences)


def _reconstruct(goal: State, came_from: dict, start: State) -> Path:
    pulls: list[Pull] = []
    state = goal
    while state in came_from:
        previous, step_pulls = came_from[state]
        pulls.extend(reversed(step_pulls))
        state = previous
    pulls.reverse()
    return Path(
        tuple(pulls),
        start.tickets_left - goal.tickets_left,
        start.catfood_draws - goal.catfood_draws,
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
    nxt = State(outcome.next_position, tickets, catfood, found)
    return nxt, step, [Pull(state.position, graph.banner_id, outcome.cat, outcome.rarity)]


def _guaranteed_move(state: State, graph: BannerGraph, config: Guaranteed, targets: frozenset[str]):
    # rolls-1 normal pulls then one guaranteed uber, for a fixed catfood cost.
    draws = config.cost // CATFOOD_PER_DRAW
    if state.catfood_draws < draws:
        return None
    position = state.position
    found = state.found
    pulls = []
    for _ in range(config.rolls - 1):
        outcome = graph.outcome(position)
        if outcome is None:
            return None
        pulls.append(Pull(position, graph.banner_id, outcome.cat, outcome.rarity))
        if not outcome.switched and outcome.cat in targets:
            found = found | {outcome.cat}
        position = outcome.next_position
    final = graph.guaranteed(position)
    if final is None:
        return None
    pulls.append(Pull(position, graph.banner_id, final.cat, final.rarity))
    if final.cat in targets:
        found = found | {final.cat}
    nxt = State(final.next_position, state.tickets_left, state.catfood_draws - draws, found)
    return nxt, config.cost, pulls


def _candidate_moves(state, graph, targets, guaranteed):
    single = _pull(state, graph, targets)
    if single is not None:
        yield single
    config = guaranteed.get(graph.banner_id) if guaranteed else None
    if config is not None:
        multi = _guaranteed_move(state, graph, config, targets)
        if multi is not None:
            yield multi


def astar(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    upper_bound: float = INF,
    guaranteed: Mapping[str, Guaranteed] | None = None,
) -> Path | None:
    """Cheapest pull plan collecting all targets, or None. A* over states.

    Pass upper_bound (e.g. a beam-search cost) to prune branches that cannot beat it.
    Pass guaranteed to also consider each banner's guaranteed multi-roll.
    """
    graphs = list(graphs)
    targets = frozenset(targets)
    occurrences = _occurrences(graphs, targets)
    g_score: dict[State, int] = {start: 0}
    came_from: dict[State, tuple] = {}
    counter = count()
    heap = [(_node_h(start, targets, occurrences, guaranteed), next(counter), 0, start)]
    while heap:
        _, _, cost, state = heapq.heappop(heap)
        if cost > g_score[state]:
            continue
        if targets <= state.found:
            return _reconstruct(state, came_from, start)
        for graph in graphs:
            for nxt, step, pulls in _candidate_moves(state, graph, targets, guaranteed):
                new_cost = cost + step
                if new_cost < g_score.get(nxt, INF):
                    h = _node_h(nxt, targets, occurrences, guaranteed)
                    if h == INF or new_cost + h > upper_bound:
                        continue
                    g_score[nxt] = new_cost
                    came_from[nxt] = (state, pulls)
                    heapq.heappush(heap, (new_cost + h, next(counter), new_cost, nxt))
    return None


def beam_search(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    width: int,
    guaranteed: Mapping[str, Guaranteed] | None = None,
) -> Path | None:
    """Keep only the `width` most promising paths each step. Fast, not guaranteed optimal."""
    graphs = list(graphs)
    targets = frozenset(targets)
    if targets <= start.found:
        return _reconstruct(start, {}, start)
    occurrences = _occurrences(graphs, targets)
    best_cost: dict[State, int] = {start: 0}
    came_from: dict[State, tuple] = {}
    best_goal: State | None = None
    best_goal_cost = INF
    frontier = [start]
    while frontier:
        ranked: list[tuple[float, State]] = []
        for state in frontier:
            cost = best_cost[state]
            for graph in graphs:
                for nxt, step, pulls in _candidate_moves(state, graph, targets, guaranteed):
                    new_cost = cost + step
                    if new_cost >= best_cost.get(nxt, INF):
                        continue
                    best_cost[nxt] = new_cost
                    came_from[nxt] = (state, pulls)
                    if targets <= nxt.found:
                        if new_cost < best_goal_cost:
                            best_goal, best_goal_cost = nxt, new_cost
                        continue
                    h = _node_h(nxt, targets, occurrences, guaranteed)
                    if h == INF:
                        continue
                    ranked.append((new_cost + h, nxt))
        ranked.sort(key=lambda item: item[0])
        frontier = [state for _, state in ranked[:width]]
    return _reconstruct(best_goal, came_from, start) if best_goal is not None else None
