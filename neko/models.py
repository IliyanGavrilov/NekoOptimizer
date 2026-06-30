from collections.abc import Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class Pull:
    """A single pull outcome."""

    position: int
    banner_id: str
    cat: str
    rarity: Rarity


@dataclass(frozen=True, slots=True)
class State:
    """A search node; frozen so it's hashable. `found` holds only wishlist targets so far."""

    position: int
    tickets_left: int
    catfood_draws: int
    found: frozenset[str]
    last_banner: str = ""  # banner of the previous pull, to count banner switches
    banner_pulls: frozenset[tuple[str, int]] = frozenset()  # pulls so far on capped banners


@dataclass(frozen=True, slots=True)
class Leg:
    """One move in a plan: a single pull or a multi-roll on one banner, and its cats."""

    banner_id: str
    kind: str  # "Single pull", "11-roll", "15-roll (guaranteed)", ...
    cost: int  # catfood spent on this leg (0 if ticket-funded)
    pulls: tuple[Pull, ...]


@dataclass(frozen=True, slots=True)
class Path:
    """A concrete pull plan and the resources it spends."""

    pulls: tuple[Pull, ...]
    tickets_used: int
    catfood_draws_used: int
    moves: tuple[Leg, ...] = ()

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
                    last.banner_id, last.kind, last.cost + move.cost, last.pulls + move.pulls
                )
            else:
                merged.append(move)
        return merged
