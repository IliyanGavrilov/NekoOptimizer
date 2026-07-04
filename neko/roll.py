# A port of godfat's gacha roll algorithm (gitlab.com/godfat/battle-cats-rolls, Apache-2.0):
# one XorShift32 value stream read on two interleaved tracks, two values per cell.

from dataclasses import dataclass

from neko.models import Banner, BannerRolls, Rarity, TrackPull
from neko.rng import xorshift

_BASE = 10000  # godfat's GachaPool::Base: rarity scores and rates are parts-per-10000.
_TRACKS = ("A", "B")  # index 0 / 1, godfat's cat.track
# Bounce rerolls land a few positions ahead; roll this many extra rows so those landing
# cells exist (a reroll's extra step is small; a handful of rows is plenty).
_LANDING_BUFFER = 4


def pick_rarity(score: int, banner: Banner) -> Rarity:
    """The rarity band ``score`` (in [0, 10000)) falls in; past Uber is Legend (catch-all)."""
    rare = banner.rates.get(Rarity.RARE, 0)
    supa = banner.rates.get(Rarity.SUPER_RARE, 0)
    uber = banner.rates.get(Rarity.UBER_SUPER_RARE, 0)
    if score < rare:
        return Rarity.RARE
    if score < rare + supa:
        return Rarity.SUPER_RARE
    if score < rare + supa + uber:
        return Rarity.UBER_SUPER_RARE
    return Rarity.LEGEND_RARE


def _pick(pool: tuple[str, ...], slot_seed: int) -> str:
    """The unit at ``slot_seed % len(pool)``; empty pool -> "" (godfat's id -1)."""
    return pool[slot_seed % len(pool)] if pool else ""


@dataclass(slots=True)
class _Cat:
    """One rolled cell in the grid (mutable so a reroll can be filled in after the fact)."""

    seq: int  # 0-based position
    track: int  # 0 = A, 1 = B
    rarity: Rarity
    rarity_seed: int
    slot_seed: int
    name: str
    steps: int = 0  # reroll iterations that produced this cat (0 = a nominal roll)
    rerolled: _Cat | None = None  # every named rare's reroll: what a dupe arrival obtains
    realized: bool = False  # the straight play chains hit this cell's reroll (godfat shows it)
    next: _Cat | None = None  # the play chain (godfat's cat.next): what the next roll obtains

    def duped(self, prev: _Cat | None) -> bool:
        """godfat's cat.rb duped?: a rare whose id repeats the previous same-track cat."""
        return (
            prev is not None
            and self.rarity is Rarity.RARE
            and self.name != ""
            and self.name == prev.name
        )


def _reroll(cat: _Cat, pool: tuple[str, ...]) -> _Cat:
    """godfat's reroll_cat: delete the dupe's slot from a pool copy and re-pick on the next
    seed step, repeating while it stays the dupe (bounded by how often the id appears)."""
    slots = list(pool)
    seed = cat.slot_seed
    slot = cat.slot_seed % len(pool)
    name = ""
    steps = 0
    for step in range(1, pool.count(cat.name) + 1):
        seed = xorshift(seed)
        del slots[slot]
        steps = step
        if not slots:
            break
        slot = seed % len(slots)
        name = slots[slot]
        if name != cat.name:
            break
    return _Cat(cat.seq, cat.track, cat.rarity, 0, seed, name, steps=steps)


def _landing(grid: list[list[_Cat]], cat: _Cat) -> _Cat | None:
    """The cell a rerolled cat's extra step lands on (godfat's next_index/next_track)."""
    steps = cat.rerolled.steps
    seq = cat.seq + (cat.track + steps) // 2 + 1
    track = ((cat.track + steps - 1) ^ 1) & 1
    return grid[seq][track] if 0 <= seq < len(grid) else None


def _build_grid(seed: int, banner: Banner, rows: int, last_cat: str = "") -> list[list[_Cat]]:
    """Roll ``rows`` positions into a grid[seq][track], filling rare-dupe rerolls.

    ``last_cat`` is the cat obtained just before this view was anchored (a dice jump,
    an applied plan): when the very first cell repeats it, that cell arrives as a dupe,
    realizing its reroll - and, through the bounce pass, any chain it sets off."""
    # godfat's Gacha advances the seed once before the first roll, so value j of the stream
    # is advance^{j+1}(seed). Two values per position across both tracks, +2 for the slot
    # of the last cell.
    values: list[int] = []
    state = seed
    for _ in range(2 * rows + 2):
        state = xorshift(state)
        values.append(state)

    grid: list[list[_Cat]] = []
    for seq in range(rows):
        row: list[_Cat] = []
        for track in (0, 1):
            index = 2 * seq + track
            rarity_seed, slot_seed = values[index], values[index + 1]
            rarity = pick_rarity(rarity_seed % _BASE, banner)
            name = _pick(banner.pool(rarity), slot_seed)
            row.append(_Cat(seq, track, rarity, rarity_seed, slot_seed, name))
        grid.append(row)

    # Every named rare cell gets its reroll up front: the reroll depends only on the
    # cell's slot seed and the pool, so whatever path makes the cell a dupe (the straight
    # chain, a bounce landing, a mid-stream start) it rerolls the same way.
    rare_pool = banner.pool(Rarity.RARE)
    for row in grid:
        for cat in row:
            if cat.rarity is Rarity.RARE and cat.name:
                cat.rerolled = _reroll(cat, rare_pool)

    # The play chain: a cell that repeats the previous same-track cat arrives as a dupe
    # there, so its predecessor obtains the reroll instead (godfat's fill_cat_links).
    for seq in range(1, rows):
        for track in (0, 1):
            cur = grid[seq][track]
            prev = grid[seq - 1][track]
            cur.realized = cur.duped(prev)
            prev.next = cur.rerolled if cur.realized else cur

    # The remembered pull that anchored this view plays the predecessor of the very
    # first roll: repeating it makes 1A itself arrive as a dupe.
    first = grid[0][0]
    if last_cat and first.rarity is Rarity.RARE and first.name and first.name == last_cat:
        first.realized = True

    # A reroll's extra step continues on the landing cell (godfat's finish_rerolled_links);
    # a landing that repeats the rerolled cat "bounces" into the landing's own reroll. A
    # bounce also realizes the landing's reroll when the chain that reaches it is itself
    # realized. Bounces always land forward, so one forward pass resolves every chain.
    for row in grid:
        for cat in row:
            if cat.rerolled is None:
                continue
            landing = _landing(grid, cat)
            if landing is None:
                continue
            if landing.duped(cat.rerolled):
                cat.rerolled.next = landing.rerolled
                landing.realized = landing.realized or cat.realized
            else:
                cat.rerolled.next = landing
    return grid


def _follow(cat: _Cat, steps: int) -> _Cat | None:
    """godfat's follow_cat: walk the play chain, or None when it runs off the rolled grid."""
    for _ in range(steps):
        cat = cat.next
        if cat is None:
            return None
    return cat


def roll_banner(
    seed: int, banner: Banner, count: int, guaranteed_rolls: int = 0, last_cat: str = ""
) -> BannerRolls:
    """Roll ``count`` positions of ``banner`` from ``seed``, mirroring godfat's grid.
    ``last_cat`` (the pull obtained just before this view) can dupe the very first cell.

    Returns every A/B cell as a normal pull, the reroll cell of every named rare (what a
    dupe arrival there obtains; ``realized`` marks the ones the straight chains actually
    hit, which are the R cells godfat renders), and - when ``guaranteed_rolls`` is set
    (the banner offers a guaranteed multi) - the guaranteed-uber columns, keyed like
    godfat's by the multi's FIRST roll: starting a guaranteed multi on a cell rolls
    ``guaranteed_rolls - 1`` cats along the play chain, then swaps the final roll for the
    uber picked by that final cell's rarity seed (godfat's fill_guaranteed; the multi
    then continues one half-step on, track flipped). ``guaranteed_rerolls`` is the same
    column for a start whose first roll arrives as a dupe: the reroll's chain ends on a
    different cell, so the awarded uber can differ.
    """
    grid = _build_grid(seed, banner, count + _LANDING_BUFFER + 2 * guaranteed_rolls, last_cat)
    uber = banner.pool(Rarity.UBER_SUPER_RARE)

    def guaranteed_from(cat: _Cat) -> TrackPull | None:
        last = _follow(cat, guaranteed_rolls - 1)
        if last is None:
            return None
        # A rerolled `last` shares its dupe cell's coordinates; the slot seed is
        # always the nominal cell's rarity seed (godfat digs the grid, not `last`).
        slot_seed = grid[last.seq][last.track].rarity_seed
        got = _pick(uber, slot_seed)
        return TrackPull(
            cat.seq + 1, _TRACKS[cat.track], got, Rarity.UBER_SUPER_RARE, seed=slot_seed
        )

    # Each pull carries the RNG state after obtaining it: a nominal roll leaves the seed
    # at its slot value; a dupe's reroll advanced `steps` further (its final value is
    # stored as the reroll's slot_seed); a guaranteed multi's swapped final draw leaves
    # it at the very value that picked the uber. Entering that state as the input seed
    # continues the play chain from its next cell.
    pulls: list[TrackPull] = []
    rerolls: list[TrackPull] = []
    guaranteed: list[TrackPull] = []
    guaranteed_rerolls: list[TrackPull] = []
    for seq in range(count):
        for track in (0, 1):
            cat = grid[seq][track]
            label = _TRACKS[track]
            pulls.append(TrackPull(seq + 1, label, cat.name, cat.rarity, seed=cat.slot_seed))
            if cat.rerolled is not None:
                rerolls.append(
                    TrackPull(
                        seq + 1,
                        label,
                        cat.rerolled.name,
                        cat.rarity,
                        seed=cat.rerolled.slot_seed,
                        steps=cat.rerolled.steps,
                        realized=cat.realized,
                    )
                )
            if guaranteed_rolls:
                got = guaranteed_from(cat)
                if got is not None:
                    guaranteed.append(got)
                if cat.rerolled is not None:
                    got = guaranteed_from(cat.rerolled)
                    if got is not None:
                        guaranteed_rerolls.append(got)
    return BannerRolls(pulls, guaranteed, rerolls, guaranteed_rerolls)
