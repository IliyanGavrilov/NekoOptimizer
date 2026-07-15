import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

CATFOOD_PER_DRAW = 150  # one paid pull = 150 catfood


class Rarity(StrEnum):
    """Unit rarities, ordered cheapest to rarest. Normal/Special are non-gacha units
    (never rolled), present only so the canonical catalogue can hold every unit."""

    NORMAL = "Normal"
    SPECIAL = "Special"
    RARE = "Rare"
    SUPER_RARE = "Super Rare"
    UBER_SUPER_RARE = "Uber Super Rare"
    LEGEND_RARE = "Legend Rare"


# The rollable rarities in band order: a pull's rarity score walks these bottom-up.
GACHA_RARITIES = (Rarity.RARE, Rarity.SUPER_RARE, Rarity.UBER_SUPER_RARE, Rarity.LEGEND_RARE)


@dataclass(frozen=True, slots=True)
class TrackPull:
    """A pull result on track "A" or "B" at a 1-based position.

    ``seed`` is the RNG state right after you get this pull. Feed it back in as the
    input seed and the next cell in the play chain becomes the new 1A - that's what
    "apply plan" jumps to, and what a cell's dice button jumps to. For a normal pull
    it doesn't depend on the banner: a clean roll uses the same two stream values no
    matter what's in the pool.

    Reroll cells (a rare that comes up as a dupe of the previous pull) also carry
    ``steps``, the extra seed values the reroll used up - the pull then moves on
    2 + steps positions instead of 2, flipping the track - and ``realized``, whether
    the straight play chain actually hits this reroll. godfat only draws those; the
    rest are "what if" cells that only some other arrival paths can trigger.

    ``rarity_seed`` is the RNG state the cell's roll started from (the value the rarity
    band is read off; the slot seed is one step on). It's the cell's stream position -
    surfaced only for the details view - and, unlike the pool-dependent name, is the
    same for every banner rolled at that cell."""

    position: int
    track: str
    cat: str
    rarity: Rarity
    seed: int = 0
    steps: int = 0
    realized: bool = False
    rarity_seed: int = 0


@dataclass(frozen=True, slots=True)
class BannerRolls:
    """A banner's normal pulls, its guaranteed-uber column, and its rare-dupe rerolls.

    ``guaranteed_rerolls`` is the guaranteed column for multis whose FIRST roll comes
    up as a dupe. The reroll jumps the chain, so the multi ends on a different cell and
    can hand you a different uber than ``guaranteed`` does at the same position.

    ``guaranteed_rolls`` is the multi length the guaranteed columns were rolled for
    (11, 15, ...; 0 when the banner runs no guarantee) - a guaranteed trace needs it to
    light the multi's own draws."""

    pulls: list[TrackPull]
    guaranteed: list[TrackPull]
    rerolls: list[TrackPull] = field(default_factory=list)
    guaranteed_rerolls: list[TrackPull] = field(default_factory=list)
    guaranteed_rolls: int = 0


def future_uber_names(count: int) -> tuple[str, ...]:
    """The placeholder names of ``count`` future ubers, in uber-pool order. godfat gives
    them negative ids and unshifts each onto the pool front (its "(-n?)" cells), so the
    pool reads Future Uber count, ..., Future Uber 2, Future Uber 1 before the real
    ubers - our Future Uber n sits exactly where godfat shows (-n?)."""
    return tuple(f"Future Uber {n}" for n in range(count, 0, -1))


_FUTURE_UBER = re.compile(r"Future Uber \d+")


def is_future_uber(cat: str) -> bool:
    """Whether this cat is a future-uber placeholder rather than a real unit."""
    return _FUTURE_UBER.fullmatch(cat) is not None


@dataclass(frozen=True)
class Banner:
    """A gacha banner: cats and drop rates (parts-per-10000) per rarity."""

    banner_id: str
    name: str
    url: str
    rates: Mapping[Rarity, int]
    pools: Mapping[Rarity, tuple[str, ...]]

    def total_rate(self) -> int:
        return sum(self.rates.values())

    def pool(self, rarity: Rarity) -> tuple[str, ...]:
        return self.pools.get(rarity, ())

    def with_future_ubers(self, count: int) -> Banner:
        """This banner with ``count`` expected-but-unreleased ubers added, matching
        godfat's add_future_ubers: placeholders are PREPENDED to the uber pool, so every
        uber cell and guaranteed draw re-lands on `seed % (len + count)` exactly like
        godfat with its "Count of future ubers" set. Rates are untouched (the pull's
        rarity never depends on the pool)."""
        if count <= 0:
            return self

        pools = dict(self.pools)
        uber = Rarity.UBER_SUPER_RARE
        pools[uber] = future_uber_names(count) + self.pool(uber)

        return Banner(self.banner_id, self.name, self.url, self.rates, pools)


@dataclass(frozen=True, slots=True)
class Pull:
    """A single pull result. A guaranteed pull is the uber a guaranteed multi gives you;
    its position is the multi's FIRST roll (where godfat's guaranteed column shows it)."""

    position: int
    banner_id: str
    cat: str
    rarity: Rarity
    guaranteed: bool = False


@dataclass(frozen=True, slots=True)
class State:
    """A search node; frozen so it's hashable. `found` holds only wishlist targets so far.

    Platinum/Legend Capsules run on their own scarce tickets, one currency each, kept apart
    from the rare-ticket/catfood budget: ``platinum_left``/``legend_left`` are those pools,
    and the pool size doubles as the pull cap (N tickets => at most N capsule pulls)."""

    position: int
    tickets_left: int
    catfood_draws: int
    found: frozenset[str]
    last_banner: str = ""  # banner of the previous pull, to count banner switches
    platinum_left: int = 0  # Platinum Capsules tickets left (their own currency)
    legend_left: int = 0  # Legend Capsules tickets left (their own currency)
    last_cat: str = ""  # what the previous pull got: a rare that repeats it will reroll


@dataclass(frozen=True, slots=True)
class Leg:
    """One move in a plan: a single pull or a multi-roll on one banner, and its cats."""

    banner_id: str
    kind: str  # "Single pull", "11-roll", "15-roll (guaranteed)", ...
    cost: int  # catfood spent on this leg (0 if ticket-funded)
    pulls: tuple[Pull, ...]
    currency: str = ""  # "platinum"/"legend" when funded by that capsule's own ticket, else ""


@dataclass(frozen=True, slots=True)
class Path:
    """A concrete pull plan and the resources it spends."""

    pulls: tuple[Pull, ...]
    tickets_used: int
    catfood_draws_used: int
    moves: tuple[Leg, ...] = ()
    platinum_used: int = 0  # Platinum Capsules tickets spent (their own currency)
    legend_used: int = 0  # Legend Capsules tickets spent (their own currency)

    def __len__(self) -> int:
        return len(self.pulls)

    @property
    def cost(self) -> int:
        """Resource cost; tickets are free so only catfood counts."""
        return self.catfood_draws_used * CATFOOD_PER_DRAW

    @property
    def cats(self) -> tuple[str, ...]:
        return tuple(pull.cat for pull in self.pulls)

    @property
    def legs(self) -> list[Leg]:
        """Moves with consecutive single pulls on the same banner merged, for display."""
        merged: list[Leg] = []
        for move in self.moves:
            last = merged[-1] if merged else None
            if (
                last is not None
                and last.kind == "Single pull"
                and move.kind == "Single pull"
                and last.banner_id == move.banner_id
            ):
                merged[-1] = Leg(
                    last.banner_id,
                    last.kind,
                    last.cost + move.cost,
                    last.pulls + move.pulls,
                    last.currency,
                )
            else:
                merged.append(move)

        return merged
