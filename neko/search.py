import heapq
from bisect import bisect_left
from collections.abc import Iterable
from itertools import count

from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Path, Pull, State

INF = float("inf")


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


def _reconstruct(goal: State, came_from: dict, start: State) -> Path:
    pulls = []
    state = goal
    while state in came_from:
        previous, banner_id, outcome = came_from[state]
        pulls.append(Pull(previous.position, banner_id, outcome.cat, outcome.rarity))
        state = previous
    pulls.reverse()
    return Path(
        tuple(pulls),
        start.tickets_left - goal.tickets_left,
        start.catfood_draws - goal.catfood_draws,
    )


def astar(graphs: Iterable[BannerGraph], targets: Iterable[str], start: State) -> Path | None:
    """Cheapest pull plan collecting all targets, or None if unreachable. A* over states."""
    graphs = list(graphs)
    targets = frozenset(targets)
    occurrences = _occurrences(graphs, targets)
    g_score: dict[State, int] = {start: 0}
    came_from: dict[State, tuple] = {}
    counter = count()
    start_h = _heuristic(start.position, start.tickets_left, targets - start.found, occurrences)
    heap = [(start_h, next(counter), 0, start)]
    while heap:
        _, _, cost, state = heapq.heappop(heap)
        if cost > g_score[state]:
            continue
        if targets <= state.found:
            return _reconstruct(state, came_from, start)
        for graph in graphs:
            outcome = graph.outcome(state.position)
            if outcome is None:
                continue
            if state.tickets_left > 0:
                tickets, catfood, step = state.tickets_left - 1, state.catfood_draws, 0
            elif state.catfood_draws > 0:
                tickets, catfood, step = 0, state.catfood_draws - 1, CATFOOD_PER_DRAW
            else:
                continue
            found = state.found
            if not outcome.switched and outcome.cat in targets:
                found = found | {outcome.cat}
            nxt = State(outcome.next_position, tickets, catfood, found)
            new_cost = cost + step
            if new_cost < g_score.get(nxt, INF):
                h = _heuristic(nxt.position, tickets, targets - found, occurrences)
                if h == INF:
                    continue
                g_score[nxt] = new_cost
                came_from[nxt] = (state, graph.banner_id, outcome)
                heapq.heappush(heap, (new_cost + h, next(counter), new_cost, nxt))
    return None
