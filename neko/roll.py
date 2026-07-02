# A port of godfat's gacha roll algorithm (gitlab.com/godfat/battle-cats-rolls, Apache-2.0):
# one XorShift32 value stream read on two interleaved tracks, two values per cell.

from dataclasses import dataclass

from neko.godfat import BannerRolls, TrackPull
from neko.models import Banner, Rarity
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
    """The unit at ``slot_seed % len(pool)``; empty pool → "" (godfat's id -1)."""
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
    rerolled: _Cat | None = None  # set on a rare dupe: the cat you actually obtain

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


def _build_grid(seed: int, banner: Banner, rows: int) -> list[list[_Cat]]:
    """Roll ``rows`` positions into a grid[seq][track], filling rare-dupe rerolls."""
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

    # A rare that repeats the previous same-track cat rerolls.
    for seq in range(1, rows):
        for track in (0, 1):
            cur = grid[seq][track]
            if cur.duped(grid[seq - 1][track]):
                cur.rerolled = _reroll(cur, banner.pool(cur.rarity))
    # If a reroll's landing cell is itself a rare dupe of the rerolled cat, it "bounces"
    # and rerolls again (godfat's fill_cat_links). Bounces always land forward, so a single
    # forward pass resolves the whole chain.
    for row in grid:
        for cat in row:
            if cat.rerolled is None:
                continue
            landing = _landing(grid, cat)
            if landing is not None and landing.rerolled is None and landing.duped(cat.rerolled):
                landing.rerolled = _reroll(landing, banner.pool(landing.rarity))
    return grid


def roll_banner(seed: int, banner: Banner, count: int, guaranteed_rolls: int = 0) -> BannerRolls:
    """Roll ``count`` positions of ``banner`` from ``seed``, mirroring godfat's grid.

    Returns every A/B cell as a normal pull, the rare-dupe reroll cell for each duplicate,
    and - when ``guaranteed_rolls`` is set (the banner offers a guaranteed multi) - the
    guaranteed-uber column: the uber each cell yields if forced to uber, which is the roll's
    rarity seed reused as the uber slot. (``guaranteed_rolls`` governs planner reachability,
    not these values, so any positive value enables the column.)
    """
    grid = _build_grid(seed, banner, count + _LANDING_BUFFER)
    uber = banner.pool(Rarity.UBER_SUPER_RARE)

    pulls: list[TrackPull] = []
    rerolls: list[TrackPull] = []
    guaranteed: list[TrackPull] = []
    for seq in range(count):
        for track in (0, 1):
            cat = grid[seq][track]
            label = _TRACKS[track]
            pulls.append(TrackPull(seq + 1, label, cat.name, cat.rarity))
            if cat.rerolled is not None:
                rerolls.append(TrackPull(seq + 1, label, cat.rerolled.name, cat.rarity))
            if guaranteed_rolls:
                got = _pick(uber, cat.rarity_seed)
                guaranteed.append(TrackPull(seq + 1, label, got, Rarity.UBER_SUPER_RARE))
    return BannerRolls(pulls, guaranteed, rerolls)
