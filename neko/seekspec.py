# What a seed search looks for, built from a banner and the player's observed pulls - the
# input both sieves take: neko/seek.py (the numpy reference) and the page's seek.wasm.
# Kept apart from the sieve so the site can hand searches out without loading numpy.

from collections.abc import Sequence
from dataclasses import dataclass

from neko.models import GACHA_RARITIES, Banner, Rarity
from neko.normal import NormalBanner

BASE = 10000  # rarity scores and rates are parts-per-10000 (godfat's GachaPool::Base)

# Past this many matches the observed pulls underdetermine the seed: stop collecting
# and have the caller ask for more rolls instead.
MAX_MATCHES = 20


@dataclass(frozen=True, slots=True)
class SeekSpec:
    """What the sieve searches for: the observed pulls as (pool index, slot) pairs, the
    pools' cumulative rate bands and sizes, and which pools reroll a dupe. The page's
    WebAssembly build of the sieve takes exactly this."""

    cats: tuple[tuple[int, int], ...]
    bands: tuple[int, ...]
    sizes: tuple[int, ...]
    rerollable: frozenset[int]


def rate_bands(banner: Banner) -> tuple[int, int, int, int, int]:
    """Cumulative band starts: a score s means GACHA_RARITIES[r] where
    bands[r] <= s < bands[r + 1], exactly like roll.pick_rarity (legend is the
    catch-all past uber, whatever the rates sum to)."""
    rare = banner.rates.get(Rarity.RARE, 0)
    supa = banner.rates.get(Rarity.SUPER_RARE, 0)
    uber = banner.rates.get(Rarity.UBER_SUPER_RARE, 0)

    return (0, rare, rare + supa, rare + supa + uber, BASE)


def pool_sizes(banner: Banner) -> tuple[int, ...]:
    return tuple(len(banner.pool(rarity)) for rarity in GACHA_RARITIES)


def seed_spec(banner: Banner, observed: Sequence[tuple[Rarity, int]]) -> SeekSpec:
    """The rare-gacha search for ``observed`` - the player's consecutive in-game pulls on
    ``banner``, oldest first, each as (rarity, slot in that rarity's pool). Only the Rare
    pool rerolls dupes, exactly like the game's rare gacha."""
    sizes = pool_sizes(banner)
    cats: list[tuple[int, int]] = []
    for rarity, slot in observed:
        if rarity not in GACHA_RARITIES:
            raise ValueError(f"{rarity} never drops from the gacha")

        index = GACHA_RARITIES.index(rarity)
        if not 0 <= slot < sizes[index]:
            raise ValueError(f"slot {slot} outside the {rarity} pool of {sizes[index]}")

        cats.append((index, slot))

    return SeekSpec(tuple(cats), rate_bands(banner), sizes, frozenset({0}))


def normal_spec(banner: NormalBanner, observed: Sequence[tuple[int, int]]) -> SeekSpec:
    """The normal-side search: ``observed`` are the player's consecutive normal-capsule
    pulls, oldest first, each as (pool index, slot in that pool). The normal seed is
    independent of the rare one, but the stream mechanics are identical."""
    sizes = tuple(len(pool.items) for pool in banner.pools)
    for pool, slot in observed:
        if not 0 <= pool < len(banner.pools):
            raise ValueError(f"{banner.name} has no pool {pool}")
        if not 0 <= slot < sizes[pool]:
            raise ValueError(f"slot {slot} outside pool {pool} of {sizes[pool]}")

    rerollable = frozenset(i for i, pool in enumerate(banner.pools) if pool.reroll)

    return SeekSpec(tuple(observed), banner.bands(), sizes, rerollable)
