from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

CATFOOD_PER_DRAW = 150  # one paid pull = 150 catfood


class Rarity(StrEnum):
    """Gacha rarities, ordered cheapest to rarest."""

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


@dataclass(frozen=True, slots=True)
class Path:
    """A concrete pull plan and the resources it spends."""

    pulls: tuple[Pull, ...]
    tickets_used: int
    catfood_draws_used: int

    def __len__(self) -> int:
        return len(self.pulls)

    @property
    def cost(self) -> int:
        """Resource cost; tickets are free so only catfood counts."""
        return self.catfood_draws_used * CATFOOD_PER_DRAW

    @property
    def cats(self) -> tuple[str, ...]:
        return tuple(pull.cat for pull in self.pulls)
