# A port of godfat's seed seeker (gitlab.com/godfat/battle-cats-rolls, Apache-2.0,
# Seeker/Seeker-VampireFlower.c): recover the hidden gacha seed from a short run of
# observed pulls by exhausting the 2^32 seed space - numpy-vectorised where the C
# fans out over threads.

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

import numpy as np

from neko.models import GACHA_RARITIES, Banner, Rarity
from neko.rng import unxorshift, xorshift

_BASE = 10000  # rarity scores and rates are parts-per-10000 (godfat's GachaPool::Base)
_SPACE = 1 << 32  # seeds are uint32: the whole space is small enough to sieve
_CHUNK = 1 << 23  # candidates per numpy pass: array sizes stay tens of MB

# Past this many matches the observed pulls underdetermine the seed: stop collecting
# and have the caller ask for more rolls instead.
MAX_MATCHES = 20

ProgressFn = Callable[[int, float], None]


@dataclass(frozen=True, slots=True)
class SeekMatch:
    """One seed that reproduces the observed pulls.

    ``seed_before`` plays the observed pulls as its opening chain from cell 1A;
    ``seed_after`` is the state after the last of them - feed it to the planner and
    the player's NEXT roll is its cell 1A. ``run`` is godfat's run type: 0 when the
    first observed pull rolled clean; 1/2 when it only matches as the visible repick
    of a dupe (the duped roll happened just before the window), the repick landing
    below (1) or at-or-above (2) the unknown shadow slot."""

    seed_before: int
    seed_after: int
    run: int


@dataclass(frozen=True, slots=True)
class SeekResult:
    """Every match found - all that exist, unless ``truncated`` cut collection short."""

    matches: tuple[SeekMatch, ...]
    truncated: bool = False


def _bands(banner: Banner) -> tuple[int, int, int, int, int]:
    """Cumulative band starts: a score s means GACHA_RARITIES[r] where
    bands[r] <= s < bands[r + 1], exactly like roll.pick_rarity (legend is the
    catch-all past uber, whatever the rates sum to)."""
    rare = banner.rates.get(Rarity.RARE, 0)
    supa = banner.rates.get(Rarity.SUPER_RARE, 0)
    uber = banner.rates.get(Rarity.UBER_SUPER_RARE, 0)

    return (0, rare, rare + supa, rare + supa + uber, _BASE)


def _sizes(banner: Banner) -> tuple[int, ...]:
    return tuple(len(banner.pool(rarity)) for rarity in GACHA_RARITIES)


def _xs(x: np.ndarray) -> np.ndarray:
    """rng.xorshift over a whole uint32 array, in place (the dtype wraps for us)."""
    x ^= x << 13
    x ^= x >> 17
    x ^= x << 15
    return x


def _slot_candidates(b: int, m: int, chunk: int) -> Iterator[tuple[np.ndarray, float]]:
    """Every uint32 congruent to b mod m, chunked with the fraction done so far: the
    stream values whose slot pick lands on the first observed slot (the C's slot
    method, its per-thread start/end juggling replaced by arange arithmetic)."""
    total = (_SPACE - 1 - b) // m + 1

    for k0 in range(0, total, chunk):
        k = np.arange(k0, min(k0 + chunk, total), dtype=np.uint64)
        i = (k * m + b).astype(np.uint32)
        if k0 == 0 and b == 0:
            i = i[1:]  # 0 is the xorshift fixed point, never a live stream value

        yield i, min(1.0, (k0 + chunk) / total)


def _rarity_candidates(lo: int, hi: int, chunk: int) -> Iterator[tuple[np.ndarray, float]]:
    """Every uint32 whose score sits in the first pull's band [lo, hi), chunked:
    block base + in-band offset for each run of 10000 (the C's rarity method)."""
    offsets = np.arange(lo, hi, dtype=np.uint64)
    blocks = -(-_SPACE // _BASE)
    step = max(1, chunk // max(1, hi - lo))

    for b0 in range(0, blocks, step):
        base = np.arange(b0, min(b0 + step, blocks), dtype=np.uint64) * _BASE
        values = (base[:, None] + offsets[None, :]).ravel()
        if b0 + step >= blocks:
            values = values[values < _SPACE]  # the last block runs past the space

        i = values.astype(np.uint32)
        if b0 == 0 and lo == 0:
            i = i[1:]

        yield i, min(1.0, (b0 + step) / blocks)


def _sieve(
    i: np.ndarray,
    state: np.ndarray,
    cats: list[tuple[int, int]],
    bands: tuple[int, ...],
    sizes: tuple[int, ...],
) -> np.ndarray:
    """Keep the candidate lanes whose remaining pulls also match: each pull reads a
    rarity value then a slot value, and a rare landing on the previous pull's slot
    repicks once from the pool minus that cat (the C's simulate_rolls - plus the
    rarity check it skips, which is nearly free here and compacts the lanes)."""
    rare_size = sizes[0]

    for j in range(1, len(cats)):
        rarity, want = cats[j]

        _xs(state)
        score = state % _BASE
        keep = (score >= bands[rarity]) & (score < bands[rarity + 1])
        i, state = i[keep], state[keep]
        if not i.size:
            break

        _xs(state)
        slot = state % sizes[rarity]
        good = slot == want
        prev_rarity, prev_slot = cats[j - 1]
        if rarity == 0 and prev_rarity == 0 and rare_size > 1:
            dupe = slot == prev_slot
            if dupe.any():
                repick_state = _xs(state[dupe])
                state[dupe] = repick_state
                repick = repick_state % (rare_size - 1)
                good[dupe] = (repick + (repick >= prev_slot)) == want

        i, state = i[good], state[good]
        if not i.size:
            break

    return i


def _verify(
    begin: int,
    cats: list[tuple[int, int]],
    bands: tuple[int, ...],
    sizes: tuple[int, ...],
    run: int,
) -> int | None:
    """The C's verify_seed: replay every observed pull from ``begin`` with full
    checks; the state after the last pull (the current seed), or None on any
    mismatch. A run 1/2 start can't check its first pull - the shadow slot it duped
    is unknown - so it just consumes the pull's three values (rarity, slot, repick)."""
    seed = begin

    for j, (rarity, want) in enumerate(cats):
        if run and j == 0:
            for _ in range(3):
                seed = xorshift(seed)
            continue

        seed = xorshift(seed)
        score = seed % _BASE
        if not bands[rarity] <= score < bands[rarity + 1]:
            return None

        seed = xorshift(seed)
        slot = seed % sizes[rarity]
        if rarity == 0 and j > 0 and sizes[0] > 1:
            prev_rarity, prev_slot = cats[j - 1]
            if prev_rarity == 0 and slot == prev_slot:
                seed = xorshift(seed)
                repick = seed % (sizes[0] - 1)
                slot = repick + (repick >= prev_slot)

        if slot != want:
            return None

    return seed


def _seek_run(
    run: int,
    cats: list[tuple[int, int]],
    bands: tuple[int, ...],
    sizes: tuple[int, ...],
    chunk: int,
    limit: int,
    progress: ProgressFn | None,
    found: list[SeekMatch],
) -> bool:
    """One pass over the seed space under one run-type reading of the first pull,
    appending matches to ``found``; True when the pass stopped at the match cap."""
    rarity, slot = cats[0]

    if run == 0:
        m, b = sizes[rarity], slot
        lo, hi = bands[rarity], bands[rarity + 1]
        # The C's determine_fastest_approach: sieve whichever candidate family is
        # smaller - stream values in the first pull's band, or on its slot residue.
        by_rarity = (_SPACE // _BASE) * (hi - lo) < (_SPACE // m) * 1.5
    else:
        # The first pull as a dupe's repick: one value later in the stream, drawn
        # mod (pool - 1), sitting below (run 1) / at-or-above (run 2) the shadow
        # slot - so the observed slot pins the repick value's residue either way.
        m, b = sizes[0] - 1, slot - (run == 2)
        by_rarity = False

    back = 1 if by_rarity else 2 + (run > 0)
    candidates = _rarity_candidates(lo, hi, chunk) if by_rarity else _slot_candidates(b, m, chunk)

    for i, fraction in candidates:
        state = i.copy()
        if by_rarity:
            _xs(state)
            keep = state % m == b
            i, state = i[keep], state[keep]

        for value in _sieve(i, state, cats, bands, sizes).tolist():
            begin = value
            for _ in range(back):
                begin = unxorshift(begin)

            end = _verify(begin, cats, bands, sizes, run)
            if end is not None:
                found.append(SeekMatch(begin, end, run))
                if len(found) > limit:
                    return True

        if progress is not None:
            progress(run, fraction)

    return False


def seek_seed(
    banner: Banner,
    observed: Sequence[tuple[Rarity, int]],
    *,
    progress: ProgressFn | None = None,
    chunk: int = _CHUNK,
    limit: int = MAX_MATCHES,
) -> SeekResult:
    """Every seed that reproduces ``observed`` - the player's consecutive in-game
    pulls on ``banner``, oldest first, each as (rarity, slot in that rarity's pool) -
    found by sieving the whole 2^32 space like godfat's Seeker-VampireFlower.

    The clean reading runs first; only when it finds nothing are the two dupe-repick
    readings of the first pull tried (the C guesses the likelier one and stops - both
    run here, so a genuinely ambiguous window reports every candidate). ``progress``
    is called after each sieved chunk with (run, fraction of that pass done). A
    ``truncated`` result hit ``limit``: the window is too short to pin the seed down,
    ask for more rolls."""
    sizes = _sizes(banner)
    cats: list[tuple[int, int]] = []
    for rarity, slot in observed:
        if rarity not in GACHA_RARITIES:
            raise ValueError(f"{rarity} never drops from the gacha")

        index = GACHA_RARITIES.index(rarity)
        if not 0 <= slot < sizes[index]:
            raise ValueError(f"slot {slot} outside the {rarity} pool of {sizes[index]}")

        cats.append((index, slot))

    if not cats:
        raise ValueError("no observed pulls to seek with")

    bands = _bands(banner)
    found: list[SeekMatch] = []
    truncated = _seek_run(0, cats, bands, sizes, chunk, limit, progress, found)

    # Nothing rolls the first pull clean: it must have arrived as a dupe's repick,
    # if it can be one. A repick is drawn from the pool minus the shadow cat, so
    # slot 0 can't land at-or-above the shadow (run 2) and the last slot can't land
    # below it (run 1).
    if not found and cats[0][0] == 0 and sizes[0] > 1:
        first_slot = cats[0][1]
        for run in (1, 2):
            if (run == 1 and first_slot == sizes[0] - 1) or (run == 2 and first_slot == 0):
                continue

            truncated |= _seek_run(run, cats, bands, sizes, chunk, limit, progress, found)

    return SeekResult(tuple(found), truncated)


def play(seed: int, banner: Banner, count: int) -> tuple[list[tuple[Rarity, int]], int]:
    """What ``count`` consecutive in-game pulls from ``seed`` give you, as the
    (rarity, slot) pairs seek_seed takes, plus the state after the last pull. This is
    the linear play stream - two values per pull, one more when a rare repeats the
    previous pull's slot and repicks - the same chain roll_banner traces through its
    A/B grid, without the grid."""
    bands = _bands(banner)
    sizes = _sizes(banner)
    pulls: list[tuple[Rarity, int]] = []
    prev_rarity, prev_slot = -1, -1

    for _ in range(count):
        seed = xorshift(seed)
        score = seed % _BASE
        rarity = (score >= bands[1]) + (score >= bands[2]) + (score >= bands[3])
        if not sizes[rarity]:
            raise ValueError(f"the {GACHA_RARITIES[rarity]} pool is empty")

        seed = xorshift(seed)
        slot = seed % sizes[rarity]
        if rarity == 0 and prev_rarity == 0 and slot == prev_slot and sizes[0] > 1:
            seed = xorshift(seed)
            repick = seed % (sizes[0] - 1)
            slot = repick + (repick >= prev_slot)

        pulls.append((GACHA_RARITIES[rarity], slot))
        prev_rarity, prev_slot = rarity, slot

    return pulls, seed
