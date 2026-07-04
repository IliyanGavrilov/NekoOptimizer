import heapq
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import count

from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Leg, Path, Pull, Rarity, State

INF = float("inf")


@dataclass(frozen=True, slots=True)
class Multi:
    """A multi-roll option: `rolls` pulls for `cost` catfood; if `guaranteed`, the last is uber."""

    rolls: int
    cost: int
    guaranteed: bool = True


def _occurrences(graphs: Iterable[BannerGraph], targets: frozenset[str]) -> dict[str, list[int]]:
    # A target counts wherever SOME path can obtain it: a cell's nominal roll, its
    # conditional reroll (a dupe arrival really obtains that cat), and the guaranteed
    # columns for both kinds of start - a guaranteed multi can obtain a target that
    # never appears as a normal roll, and its spot is where the multi must START.
    # Extra spots only weaken the lower bound; missing ones would break admissibility.
    spots: dict[str, list[int]] = {target: [] for target in targets}
    for graph in graphs:
        for position in graph.positions():
            nominal = graph.resolve(position)
            if nominal.cat in targets:
                spots[nominal.cat].append(position)
            reroll = graph.reroll(position)
            if reroll is not None and reroll.cat in targets:
                spots[reroll.cat].append(position)
        for duped in (False, True):
            for position in graph.guaranteed_positions(duped):
                forced = graph.guaranteed(position, duped)
                if forced.cat in targets:
                    spots[forced.cat].append(position)
    for positions in spots.values():
        positions.sort()
    return spots


def obtainable(graphs: Iterable[BannerGraph], targets: Iterable[str]) -> frozenset[str]:
    """The targets that occur anywhere in the graphs - as a nominal roll, a conditional
    reroll, or a guaranteed-column uber. A target with no occurrence can never be
    collected whatever the budget, so callers can drop it before searching: every such
    target DOUBLES a subset enumeration without ever contributing a plan."""
    graphs = list(graphs)
    spots = _occurrences(graphs, frozenset(targets))
    return frozenset(cat for cat, positions in spots.items() if positions)


def _multi_landing(graph: BannerGraph, position: int, rolls: int, last_cat: str = "") -> int | None:
    """Where a guaranteed multi started at ``position`` continues: walk its ``rolls - 1``
    real rolls along the chain, then one half-step past the swapped final roll (track
    flips with the parity). None when the chain runs off the rolled window."""
    for _ in range(rolls - 1):
        outcome = graph.resolve(position, last_cat)
        if outcome is None:
            return None
        last_cat = outcome.cat
        position = outcome.next_position
    return position + 1


def _canon_last(graphs: Iterable[BannerGraph], position: int, last_cat: str) -> str:
    """The previously obtained cat only matters where the next roll could repeat it;
    dropping it everywhere else lets converging search paths share one state."""
    if not last_cat:
        return ""
    for graph in graphs:
        nominal = graph.resolve(position)
        if nominal is not None and nominal.rarity is Rarity.RARE and nominal.cat == last_cat:
            return last_cat
    return ""


def _canon(state: State, graphs: Iterable[BannerGraph]) -> State:
    last = _canon_last(graphs, state.position, state.last_cat)
    return state if last == state.last_cat else replace(state, last_cat=last)


def _collectable(
    graphs: list[BannerGraph],
    targets: frozenset[str],
    position: int,
    multis: Mapping[str, Sequence[Multi]] | None = None,
    last_cat: str = "",
    occurrences: dict[str, list[int]] | None = None,
) -> bool:
    """Ignoring budget, can every target still be collected from ``position``? BFS over
    (position, last cat, found) using the graphs' real step structure - rare-dupe
    rerolls force extra steps, so a spot's parity can make it genuinely unreachable, and
    the full search would only prove that after exhausting every budget split of the
    whole state space. Guaranteed multis are modelled with their real landing so their
    off-parity continue points stay reachable.

    Pass ``occurrences`` (each target's obtain spots, as [_occurrences] returns them)
    to reuse the caller's; a target with no spot at or past ``position`` is a plain
    "no" without any BFS."""
    if not targets:
        return True
    spots = occurrences if occurrences is not None else _occurrences(graphs, targets)
    for target in targets:
        places = spots[target]
        if bisect_left(places, position) == len(places):
            return False
    rolls_by_banner = {
        banner_id: sorted({m.rolls for m in ms if m.guaranteed})
        for banner_id, ms in (multis or {}).items()
    }
    start = (position, _canon_last(graphs, position, last_cat))
    # Per (position, last cat), only the maximal found-sets: a path arriving with a
    # subset of another's finds can do nothing the other can't (moves depend only on
    # position and last cat, and found only grows), so the whole 2^targets lattice
    # never needs walking. Without this the BFS itself explodes past ~8 targets.
    seen: dict[tuple[int, str], list[frozenset[str]]] = {start: [frozenset()]}
    frontier = [(*start, frozenset())]
    while frontier:
        upcoming = []
        for pos, last, found in frontier:
            for graph in graphs:
                moves = []
                outcome = graph.resolve(pos, last)
                if outcome is not None:
                    moves.append((outcome.cat, outcome.next_position))
                    forced = graph.guaranteed(pos, duped=outcome.switched)
                    if forced is not None:
                        for rolls in rolls_by_banner.get(graph.banner_id, ()):
                            landing = _multi_landing(graph, pos, rolls, last)
                            if landing is not None:
                                moves.append((forced.cat, landing))
                for cat, next_position in moves:
                    got = found | {cat} if cat in targets else found
                    if got >= targets:
                        return True
                    key = (next_position, _canon_last(graphs, next_position, cat))
                    kept = seen.setdefault(key, [])
                    if any(got <= other for other in kept):
                        continue
                    kept[:] = [other for other in kept if not other <= got]
                    kept.append(got)
                    upcoming.append((*key, got))
        frontier = upcoming
    return False


def _multi_floor(multis: Mapping[str, Sequence[Multi]] | None) -> float:
    """The cheapest per-pull catfood any multi achieves (INF when there are none) -
    the floor a multi-using plan can undercut single-pull prices to."""
    return min((m.cost / m.rolls for ms in (multis or {}).values() for m in ms), default=INF)


def _heuristic(
    position: int,
    tickets_left: int,
    remaining: frozenset[str],
    occurrences: dict[str, list[int]],
    ticket_value: int,
    multi_floor: float = INF,
    advance: int = 3,
) -> float:
    # Lower-bound the pulls to the farthest still-needed target: each pull advances the
    # position by at most `advance` (+2 nominal, +2+steps on the banners' worst reroll),
    # so reaching a target d away costs at least d // advance + 1 pulls.
    worst = 0
    for cat in remaining:
        spots = occurrences[cat]
        index = bisect_left(spots, position)
        if index == len(spots):
            return INF
        worst = max(worst, (spots[index] - position) // advance + 1)
    if worst == 0:
        return 0.0
    # The cheapest any pull can be: a multi's per-roll price when that undercuts a full
    # draw, and for up to tickets_left of them a ticket priced at min(value, draw).
    # Capping the ticket price keeps this a true lower bound even when tickets are dear.
    floor = min(CATFOOD_PER_DRAW, multi_floor)
    cheapest = min(ticket_value, floor)
    ticketed = min(worst, tickets_left)
    return ticketed * cheapest + (worst - ticketed) * floor


def _node_h(
    state: State,
    targets: frozenset[str],
    occurrences,
    ticket_value: int,
    multi_floor: float,
    advance: int = 3,
) -> float:
    return _heuristic(
        state.position,
        state.tickets_left,
        targets - state.found,
        occurrences,
        ticket_value,
        multi_floor,
        advance,
    )


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


def _banner_pulls(state: State, banner_id: str) -> int:
    for bid, used in state.banner_pulls:
        if bid == banner_id:
            return used
    return 0


def _bump(
    counts: frozenset[tuple[str, int]], banner_id: str, delta: int
) -> frozenset[tuple[str, int]]:
    # Add `delta` to one banner's running pull count (only tracked for capped banners).
    used = {bid: n for bid, n in counts}
    used[banner_id] = used.get(banner_id, 0) + delta
    return frozenset(used.items())


def _pull_variants(
    state: State,
    graph: BannerGraph,
    targets: frozenset[str],
    limit: int | None,
    ticket_value: int,
):
    # Each affordable way to pull `graph` once at `state`: a ticket-funded move and/or a
    # catfood-funded one. They reach the same outcome, differing only in what they spend.
    outcome = graph.resolve(state.position, state.last_cat)
    if outcome is None:
        return
    if limit is not None and _banner_pulls(state, graph.banner_id) >= limit:
        return
    found = state.found
    if outcome.cat in targets:
        found = found | {outcome.cat}
    pull = Pull(state.position, graph.banner_id, outcome.cat, outcome.rarity)
    counts = state.banner_pulls if limit is None else _bump(state.banner_pulls, graph.banner_id, 1)
    can_ticket = state.tickets_left > 0
    can_catfood = state.catfood_draws > 0
    # Funding order never changes a finished plan's totals (a single costs one ticket or
    # one draw whenever it happens, and budgets only shrink), and hoarding catfood can
    # only help later multis - so when tickets aren't dearer than a draw, spend them
    # first and don't fork the search into every ticket/catfood split (which explodes
    # the state space). Dearer tickets really trade off against future multis, so those
    # keep both branches.
    if can_ticket and can_catfood and ticket_value <= CATFOOD_PER_DRAW:
        can_catfood = False
    if can_ticket:
        nxt = State(
            outcome.next_position,
            state.tickets_left - 1,
            state.catfood_draws,
            found,
            graph.banner_id,
            counts,
            outcome.cat,
        )
        yield nxt, Leg(graph.banner_id, "Single pull", 0, (pull,))
    if can_catfood:
        nxt = State(
            outcome.next_position,
            state.tickets_left,
            state.catfood_draws - 1,
            found,
            graph.banner_id,
            counts,
            outcome.cat,
        )
        yield nxt, Leg(graph.banner_id, "Single pull", CATFOOD_PER_DRAW, (pull,))


def _multi_move(
    state: State, graph: BannerGraph, multi: Multi, targets: frozenset[str], limit: int | None
):
    # `rolls` normal pulls (the last swapped for the guaranteed uber if guaranteed),
    # for a fixed catfood cost. The guaranteed uber is the column value at the multi's
    # FIRST roll (godfat semantics) - the duped column when the first roll arrives as a
    # dupe, since the reroll's chain ends on a different cell; the multi then continues
    # one half-step past where the swapped final roll would have been, flipping the track.
    draws = multi.cost // CATFOOD_PER_DRAW
    if state.catfood_draws < draws:
        return None
    if limit is not None and _banner_pulls(state, graph.banner_id) + multi.rolls > limit:
        return None
    first = graph.resolve(state.position, state.last_cat)
    if first is None:
        return None
    forced = graph.guaranteed(state.position, duped=first.switched) if multi.guaranteed else None
    if multi.guaranteed and forced is None:
        return None
    position = state.position
    last = state.last_cat
    found = state.found
    pulls = []
    normal_rolls = multi.rolls - 1 if multi.guaranteed else multi.rolls
    for _ in range(normal_rolls):
        outcome = graph.resolve(position, last)
        if outcome is None:
            return None
        pulls.append(Pull(position, graph.banner_id, outcome.cat, outcome.rarity))
        if outcome.cat in targets:
            found = found | {outcome.cat}
        last = outcome.cat
        position = outcome.next_position
    if multi.guaranteed:
        pulls.append(
            Pull(state.position, graph.banner_id, forced.cat, forced.rarity, guaranteed=True)
        )
        if forced.cat in targets:
            found = found | {forced.cat}
        last = forced.cat
        position += 1
    counts = (
        state.banner_pulls
        if limit is None
        else _bump(state.banner_pulls, graph.banner_id, multi.rolls)
    )
    nxt = State(
        position,
        state.tickets_left,
        state.catfood_draws - draws,
        found,
        graph.banner_id,
        counts,
        last,
    )
    kind = f"{multi.rolls}-roll" + (" (guaranteed)" if multi.guaranteed else "")
    return nxt, Leg(graph.banner_id, kind, multi.cost, tuple(pulls))


def _switch(state: State, leg: Leg) -> int:
    # 1 if this leg rolls a different banner than the previous pull (the first pull is free).
    return 1 if state.last_banner and state.last_banner != leg.banner_id else 0


def _candidate_moves(state, graph, targets, multis, banner_limits, ticket_value):
    limit = banner_limits.get(graph.banner_id) if banner_limits else None
    yield from _pull_variants(state, graph, targets, limit, ticket_value)
    for multi in multis.get(graph.banner_id, ()) if multis else ():
        move = _multi_move(state, graph, multi, targets, limit)
        if move is not None:
            yield move


def _step_cost(state: State, nxt: State, leg: Leg, ticket_value: int):
    """Lexicographic cost of one move: (catfood-equivalent, switches, catfood spent).

    Tickets and catfood are folded into one number via ticket_value; remaining ties go
    to the plan spending less catfood (tickets only fund singles, catfood also funds
    multis, so catfood is the resource worth keeping)."""
    tickets = state.tickets_left - nxt.tickets_left
    catfood = (state.catfood_draws - nxt.catfood_draws) * CATFOOD_PER_DRAW
    equivalent = catfood + tickets * ticket_value
    return equivalent, _switch(state, leg), catfood


def astar(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    upper_bound: float = INF,
    multis: Mapping[str, Sequence[Multi]] | None = None,
    ticket_value: int = CATFOOD_PER_DRAW,
    banner_limits: Mapping[str, int] | None = None,
) -> Path | None:
    """Cheapest pull plan collecting all targets, or None. A* over states.

    Pass upper_bound (e.g. a beam-search cost) to prune branches that cannot beat it.
    Pass multis to also consider each banner's multi-roll options. ticket_value prices a
    rare ticket in catfood: tickets are spent first unless dearer than a draw.
    banner_limits caps the total pulls allowed on a banner (0 excludes it entirely).
    """
    graphs = list(graphs)
    targets = frozenset(targets)
    occurrences = _occurrences(graphs, targets)
    needed = targets - start.found
    if not _collectable(graphs, needed, start.position, multis, start.last_cat, occurrences):
        return None
    floor = _multi_floor(multis)
    advance = max((graph.max_advance() for graph in graphs), default=3)
    # Lexicographic g (catfood-equivalent, switches, catfood spent): cheapest first,
    # then fewest banner switches, then the least catfood (it also funds multis).
    g_score: dict[State, tuple[int, int, int]] = {start: (0, 0, 0)}
    came_from: dict[State, tuple] = {}
    counter = count()
    h0 = _node_h(start, targets, occurrences, ticket_value, floor, advance)
    heap = [((h0, 0, 0), next(counter), (0, 0, 0), start)]
    while heap:
        _, _, g, state = heapq.heappop(heap)
        if g > g_score[state]:
            continue
        if targets <= state.found:
            return _reconstruct(state, came_from, start)
        for graph in graphs:
            moves = _candidate_moves(state, graph, targets, multis, banner_limits, ticket_value)
            for nxt, leg in moves:
                nxt = _canon(nxt, graphs)
                dc, ds, dd = _step_cost(state, nxt, leg, ticket_value)
                new_g = (g[0] + dc, g[1] + ds, g[2] + dd)
                if new_g < g_score.get(nxt, (INF, INF, INF)):
                    h = _node_h(nxt, targets, occurrences, ticket_value, floor, advance)
                    if h == INF or new_g[0] + h > upper_bound:
                        continue
                    g_score[nxt] = new_g
                    came_from[nxt] = (state, leg)
                    priority = (new_g[0] + h, new_g[1], new_g[2])
                    heapq.heappush(heap, (priority, next(counter), new_g, nxt))
    return None


def beam_search(
    graphs: Iterable[BannerGraph],
    targets: Iterable[str],
    start: State,
    width: int,
    multis: Mapping[str, Sequence[Multi]] | None = None,
    ticket_value: int = CATFOOD_PER_DRAW,
    banner_limits: Mapping[str, int] | None = None,
    upper_bound: float = INF,
) -> Path | None:
    """Keep only the `width` most promising paths each step. Fast, not guaranteed optimal."""
    graphs = list(graphs)
    targets = frozenset(targets)
    if targets <= start.found:
        return _reconstruct(start, {}, start)
    occurrences = _occurrences(graphs, targets)
    # Only the cheap "does every target still occur ahead" guard here, not the exact
    # reachability BFS: the frontier is width-capped, so an uncollectable target set
    # just runs off the rolled window and returns None anyway - the exact pre-check
    # can cost more than the whole beam.
    for target in targets - start.found:
        spots = occurrences[target]
        if bisect_left(spots, start.position) == len(spots):
            return None
    floor = _multi_floor(multis)
    advance = max((graph.max_advance() for graph in graphs), default=3)
    # Lexicographic g (catfood-equivalent, switches, catfood spent); see astar.
    best_cost: dict[State, tuple[int, int, int]] = {start: (0, 0, 0)}
    came_from: dict[State, tuple] = {}
    best_goal: State | None = None
    best_goal_cost = (INF, INF, INF)
    frontier = [start]
    while frontier:
        ranked: list[tuple[float, int, int, State]] = []
        for state in frontier:
            g = best_cost[state]
            for graph in graphs:
                moves = _candidate_moves(state, graph, targets, multis, banner_limits, ticket_value)
                for nxt, leg in moves:
                    nxt = _canon(nxt, graphs)
                    dc, ds, dd = _step_cost(state, nxt, leg, ticket_value)
                    new_g = (g[0] + dc, g[1] + ds, g[2] + dd)
                    if new_g >= best_cost.get(nxt, (INF, INF, INF)):
                        continue
                    best_cost[nxt] = new_g
                    came_from[nxt] = (state, leg)
                    if targets <= nxt.found:
                        if new_g < best_goal_cost:
                            best_goal, best_goal_cost = nxt, new_g
                        continue
                    h = _node_h(nxt, targets, occurrences, ticket_value, floor, advance)
                    if h == INF or new_g[0] + h > upper_bound:
                        continue
                    ranked.append((new_g[0] + h, new_g[1], new_g[2], nxt))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        frontier = [state for *_, state in ranked[:width]]
    return _reconstruct(best_goal, came_from, start) if best_goal is not None else None
