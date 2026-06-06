"""Typed data models shared across the optimizer.

Kept deliberately small: just the four core records (Banner, Pull, State, Path)
plus the Rarity enum. Behaviour that depends on the seed stream (rolling a
rarity, switching tracks) lives in the graph builder, not here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

CATFOOD_PER_DRAW = 150  # one paid pull = 150 catfood


class Rarity(str, Enum):
    """Gacha rarities, ordered cheapest to rarest."""

    RARE = "Rare"
    SUPER_RARE = "Super Rare"
    UBER_SUPER_RARE = "Uber Super Rare"
    LEGEND_RARE = "Legend Rare"


@dataclass(frozen=True)
class Banner:
    """A gacha banner: which cats drop at each rarity and at what rate.

    Not hashable (it holds mappings); banners are looked up by id, not put in
    sets. Rates are parts-per-10000 and should sum to 10000 for a valid banner.
    """

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
    """The outcome of a single pull at a given position in the seed stream."""

    position: int
    banner_id: str
    cat: str
    rarity: Rarity


@dataclass(frozen=True, slots=True)
class State:
    """A node in the search graph.

    Frozen + slotted so it is hashable (it keys the A* score/visited dicts) and
    cheap to allocate in bulk. `found` holds only the wishlist targets collected
    so far, so equal progress collapses to the same node.
    """

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
        """Resource cost. Tickets are free, so only catfood counts."""
        return self.catfood_draws_used * CATFOOD_PER_DRAW

    @property
    def cats(self) -> tuple[str, ...]:
        return tuple(pull.cat for pull in self.pulls)
