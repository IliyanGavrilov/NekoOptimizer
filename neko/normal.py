# The normal-side gacha (Normal Capsules and its event variants): the SAME xorshift
# stream mechanics as the rare gacha, but on its own independent seed, with items
# instead of cats and an arbitrary stack of rate bands ("pools") per banner - only
# some of which reroll dupes. Banner data verified against ampuri's tracker
# (github.com/ampuri/bc-normal-seed-tracking, the community reference for the
# normal seed), which this module is checked against by the golden tests.

from dataclasses import dataclass

from neko.rng import xorshift

_BASE = 10000  # rates are parts-per-10000, exactly like the rare gacha
_TRACKS = ("A", "B")
# Bounce rerolls land a few positions ahead; roll this many extra rows so those
# landing cells exist (a cascade consumes at most a handful of steps).
_LANDING_BUFFER = 4


@dataclass(frozen=True, slots=True)
class NormalPool:
    """One rate band of a normal-side banner: its share of 10000, its ordered items,
    and whether a dupe landing in it rerolls (only some bands do - e.g. the Catseye
    banner rerolls its common band but hands you a duplicate Uber Catseye happily)."""

    rate: int
    items: tuple[str, ...]
    reroll: bool


@dataclass(frozen=True, slots=True)
class NormalBanner:
    """A normal-side banner: an ordered stack of rate bands. A pull's rarity score
    (seed % 10000) walks the bands bottom-up, then its slot picks from that band."""

    key: str  # short id used in URLs and posts ("n", "ce", ...)
    name: str
    pools: tuple[NormalPool, ...]

    def bands(self) -> tuple[int, ...]:
        """Cumulative band starts, one entry per pool plus the closing _BASE: a score
        s falls in pool p when bands[p] <= s < bands[p + 1]."""
        starts = [0]
        for pool in self.pools:
            starts.append(starts[-1] + pool.rate)

        return tuple(starts)


# The upgrade items sold between the cats in the plain capsule pools ("Special
# Skills" in game); the page styles them apart from the cats.
UPGRADES = (
    "Cat Cannon Attack",
    "Cat Cannon Charge",
    "Worker Cat Rate",
    "Worker Cat Wallet",
    "Base Defense",
    "Research",
    "Accounting",
    "Study",
    "Cat Energy",
)

_NORMAL_CATS = (
    "Cat",
    "Tank Cat",
    "Axe Cat",
    "Gross Cat",
    "Cow Cat",
    "Bird Cat",
    "Fish Cat",
    "Lizard Cat",
    "Titan Cat",
)

NORMAL_BANNERS = (
    NormalBanner("n", "Normal Capsules", (NormalPool(_BASE, _NORMAL_CATS + UPGRADES, True),)),
    NormalBanner(
        "np",
        "Normal Capsules+",
        (NormalPool(_BASE, _NORMAL_CATS + ("Superfeline",) + UPGRADES, True),),
    ),
    NormalBanner(
        "cf",
        "Catfruit Capsules",
        (
            NormalPool(400, ("5K XP",), False),
            NormalPool(
                2000,
                (
                    "Speed Up",
                    "Cat CPU",
                    "10K XP",
                    "30K XP",
                    "50K XP",
                    "Purple Catfruit Seed",
                    "Red Catfruit Seed",
                    "Blue Catfruit Seed",
                    "Green Catfruit Seed",
                    "Yellow Catfruit Seed",
                ),
                True,
            ),
            NormalPool(
                7000,
                (
                    "Rich Cat",
                    "Cat Jobs",
                    "Sniper the Cat",
                    "100K XP",
                    "200K XP",
                    "Purple Catfruit",
                    "Red Catfruit",
                    "Blue Catfruit",
                    "Green Catfruit",
                    "Yellow Catfruit",
                ),
                False,
            ),
            NormalPool(600, ("Treasure Radar", "500K XP", "Epic Catfruit"), False),
        ),
    ),
    NormalBanner(
        "ce",
        "Catseye Capsules",
        (
            NormalPool(500, ("5K XP",), False),
            NormalPool(6900, ("10K XP", "30K XP", "Special Catseye", "Rare Catseye"), True),
            NormalPool(2000, ("100K XP", "Super Rare Catseye"), False),
            NormalPool(500, ("Uber Rare Catseye",), False),
            NormalPool(100, ("Dark Catseye",), False),
        ),
    ),
    NormalBanner(
        "lt",
        "Lucky Ticket",
        (
            NormalPool(0, (), False),
            NormalPool(
                7400,
                (
                    "Li'l Titan Cat",
                    "Li'l Lizard Cat",
                    "Li'l Fish Cat",
                    "Li'l Bird Cat",
                    "Li'l Cow Cat",
                    "Li'l Gross Cat",
                    "Li'l Axe Cat",
                    "Li'l Tank Cat",
                    "Li'l Cat",
                    "Speed Up",
                    "Speed Up",
                    "Speed Up",
                    "Cat CPU",
                    "Cat CPU",
                    "10K XP",
                    "10K XP",
                    "10K XP",
                    "30K XP",
                    "30K XP",
                    "30K XP",
                ),
                True,
            ),
            NormalPool(2100, ("Rich Cat", "Cat Jobs", "Sniper the Cat"), False),
            NormalPool(500, ("Treasure Radar",), False),
        ),
    ),
    NormalBanner(
        "ltg",
        "Lucky Ticket G",
        (
            NormalPool(0, (), False),
            NormalPool(
                5100,
                (
                    "Catamin A",
                    "Catamin A",
                    "Catamin A",
                    "100K XP (β)",
                    "100K XP (β)",
                    "100K XP (β)",
                ),
                True,
            ),
            NormalPool(3500, ("Catamin B", "Catamin B", "Catamin B", "500K XP"), False),
            NormalPool(1400, ("Catamin C", "Catamin C", "Catamin C", "1M XP"), False),
        ),
    ),
)

BANNERS_BY_KEY = {banner.key: banner for banner in NORMAL_BANNERS}

# Banners the normal seed finder offers: every item name in them is unique, so an
# observed item pins exactly one (pool, slot) - the lucky tickets repeat items
# across slots and would need every copy tried one by one.
SEEKABLE_KEYS = ("n", "np", "cf", "ce")


def pick_pool(score: int, banner: NormalBanner) -> int:
    """The pool index ``score`` (in [0, 10000)) falls in."""
    bands = banner.bands()
    for index in range(len(banner.pools)):
        if score < bands[index + 1]:
            return index

    return len(banner.pools) - 1


@dataclass(frozen=True, slots=True)
class NormalPull:
    """One cell of the normal tracks, mirroring TrackPull: ``seed`` is the RNG state
    right after you get this pull (feed it back in and the play chain continues);
    reroll cells also carry ``steps`` (extra values the cascade used) and
    ``realized`` (the straight play chain actually hits this reroll)."""

    position: int
    track: str
    item: str
    pool: int
    seed: int = 0
    steps: int = 0
    realized: bool = False


@dataclass(frozen=True, slots=True)
class NormalRolls:
    """A normal banner's rolled tracks: every A/B cell plus the reroll branch of
    every cell whose pool rerolls dupes."""

    pulls: list[NormalPull]
    rerolls: list[NormalPull]


@dataclass(slots=True)
class _Item:
    """One rolled cell in the grid (mutable so a reroll can be filled in after)."""

    seq: int  # 0-based position
    track: int  # 0 = A, 1 = B
    pool: int
    slot_seed: int
    name: str
    reroll: bool  # the cell's pool rerolls dupes
    steps: int = 0  # cascade iterations that produced this item (0 = a nominal roll)
    rerolled: _Item | None = None  # what a dupe landing here gets instead
    realized: bool = False  # the straight play chain hits this cell's reroll

    def duped(self, prev: _Item | None) -> bool:
        """A pull in a rerolling pool whose item repeats the previous same-track
        pull's item - the trigger compares NAMES, so the lucky tickets' repeated
        slots dupe each other (ampuri's lastRoll check)."""
        return prev is not None and self.reroll and self.name != "" and self.name == prev.name


def _reroll(item: _Item, pool: tuple[str, ...]) -> _Item:
    """Delete the dupe's slot from a pool copy and re-pick on the next seed step,
    repeating while it stays the dupe (bounded by how often the name appears) -
    the same cascade as the rare gacha's reroll_cat."""
    slots = list(pool)
    seed = item.slot_seed
    slot = item.slot_seed % len(pool)
    name = ""
    steps = 0

    for step in range(1, pool.count(item.name) + 1):
        seed = xorshift(seed)
        del slots[slot]
        steps = step

        if not slots:
            break

        slot = seed % len(slots)
        name = slots[slot]

        if name != item.name:
            break

    return _Item(item.seq, item.track, item.pool, seed, name, item.reroll, steps=steps)


def landing(position: int, track: str, steps: int) -> tuple[int, str]:
    """The 1-based cell a reroll's extra ``steps`` land the chain on (the same
    arithmetic as the rare grid: 2 + steps values on from the dupe cell, the track
    flipping with the step parity)."""
    index = _TRACKS.index(track)

    return position + (index + steps) // 2 + 1, _TRACKS[((index + steps - 1) ^ 1) & 1]


def _landing(grid: list[list[_Item]], item: _Item) -> _Item | None:
    """The grid cell a rerolled item's extra steps land on, if it was rolled."""
    position, track = landing(item.seq + 1, _TRACKS[item.track], item.rerolled.steps)
    seq = position - 1

    return grid[seq][_TRACKS.index(track)] if 0 <= seq < len(grid) else None


def _build_grid(
    seed: int, banner: NormalBanner, rows: int, last_item: str = ""
) -> list[list[_Item]]:
    """Roll ``rows`` positions into a grid[seq][track], filling in dupe rerolls.

    ``last_item`` is the pull you got just before this view starts: when the very
    first cell repeats it, that cell comes up as a dupe, which turns on its reroll -
    and, through the bounce pass, any chain that sets off."""
    values: list[int] = []
    state = seed

    for _ in range(2 * rows + 2):
        state = xorshift(state)
        values.append(state)

    bands = banner.bands()
    grid: list[list[_Item]] = []
    for seq in range(rows):
        row: list[_Item] = []
        for track in (0, 1):
            index = 2 * seq + track
            rarity_seed, slot_seed = values[index], values[index + 1]
            score = rarity_seed % _BASE
            pool_index = 0
            while score >= bands[pool_index + 1]:
                pool_index += 1

            pool = banner.pools[pool_index]
            name = pool.items[slot_seed % len(pool.items)] if pool.items else ""
            row.append(_Item(seq, track, pool_index, slot_seed, name, pool.reroll))
        grid.append(row)

    # Every named cell in a rerolling pool gets its reroll up front: it depends only
    # on the cell's slot seed and the pool, whatever path makes the cell a dupe.
    for row in grid:
        for item in row:
            if item.reroll and item.name:
                item.rerolled = _reroll(item, banner.pools[item.pool].items)

    # The straight play chains: a cell that repeats the previous same-track item
    # comes up as a dupe there.
    for seq in range(1, rows):
        for track in (0, 1):
            grid[seq][track].realized = grid[seq][track].duped(grid[seq - 1][track])

    first = grid[0][0]
    if last_item and first.reroll and first.name and first.name == last_item:
        first.realized = True

    # A reroll's extra step continues on the landing cell; a landing that repeats
    # the rerolled item bounces into the landing's own reroll. Bounces always land
    # forward, so one forward pass resolves every chain.
    for row in grid:
        for item in row:
            if item.rerolled is None:
                continue

            landing = _landing(grid, item)
            if landing is not None and landing.duped(item.rerolled):
                landing.realized = landing.realized or item.realized

    return grid


def roll_normal(seed: int, banner: NormalBanner, count: int, last_item: str = "") -> NormalRolls:
    """Roll ``count`` positions of ``banner`` from ``seed``, as the A/B grid the
    normal tracks page draws. ``last_item`` (the pull you got just before this view)
    can dupe the very first cell."""
    grid = _build_grid(seed, banner, count + _LANDING_BUFFER, last_item)

    pulls: list[NormalPull] = []
    rerolls: list[NormalPull] = []
    for seq in range(count):
        for track in (0, 1):
            item = grid[seq][track]
            label = _TRACKS[track]
            pulls.append(NormalPull(seq + 1, label, item.name, item.pool, seed=item.slot_seed))

            if item.rerolled is not None:
                rerolls.append(
                    NormalPull(
                        seq + 1,
                        label,
                        item.rerolled.name,
                        item.pool,
                        seed=item.rerolled.slot_seed,
                        steps=item.rerolled.steps,
                        realized=item.realized,
                    )
                )

    return NormalRolls(pulls, rerolls)


def play(seed: int, banner: NormalBanner, count: int, last_item: str = "") -> tuple[list[str], int]:
    """What ``count`` consecutive pulls from ``seed`` give you - the linear play
    stream: two values per pull, plus the cascade's extras when a pull in a
    rerolling pool repeats the previous pull's item. Returns the item names and the
    state after the last pull."""
    bands = banner.bands()
    items: list[str] = []
    prev = last_item

    for _ in range(count):
        seed = xorshift(seed)
        score = seed % _BASE
        pool_index = 0
        while score >= bands[pool_index + 1]:
            pool_index += 1

        pool = banner.pools[pool_index]
        if not pool.items:
            raise ValueError(f"pool {pool_index} of {banner.name} is empty")

        seed = xorshift(seed)
        slots = list(pool.items)
        name = slots[seed % len(slots)]
        if pool.reroll and name and name == prev:
            slot = seed % len(slots)
            for _ in range(pool.items.count(name)):
                seed = xorshift(seed)
                del slots[slot]
                if not slots:
                    break

                slot = seed % len(slots)
                if slots[slot] != name:
                    break

            name = slots[slot] if slots else ""

        items.append(name)
        prev = name

    return items, seed
