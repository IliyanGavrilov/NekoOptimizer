import pytest

from neko.models import Banner, Rarity
from neko.normal import BANNERS_BY_KEY, NormalBanner, NormalPool
from neko.normal import play as normal_play
from neko.rng import xorshift
from neko.roll import roll_banner
from neko.seek import play, seek_normal, seek_seed
from neko.tests.test_golden import local_banner

GOLDEN_SEED = 1893568593

# All-rare synthetic banner: a huge pool keeps the sieve's candidate family tiny
# (2^32 / 3000), so full-space seeks run in milliseconds instead of seconds.
ALL_RARE = Banner(
    "all-rare",
    "all rare",
    "",
    {Rarity.RARE: 10000},
    {Rarity.RARE: tuple(f"R{i}" for i in range(3000))},
)

# A narrow legend band over a big legend pool makes the band the cheaper candidate
# family, forcing the C's rarity method (a rare/supa/uber first pull picks the slot
# residue method instead).
LEGEND_HEAVY = Banner(
    "legend-heavy",
    "legend heavy",
    "",
    {
        Rarity.RARE: 6000,
        Rarity.SUPER_RARE: 2000,
        Rarity.UBER_SUPER_RARE: 1970,
        Rarity.LEGEND_RARE: 30,
    },
    {
        Rarity.RARE: tuple(f"R{i}" for i in range(300)),
        Rarity.SUPER_RARE: tuple(f"S{i}" for i in range(200)),
        Rarity.UBER_SUPER_RARE: tuple(f"U{i}" for i in range(100)),
        Rarity.LEGEND_RARE: tuple(f"L{i}" for i in range(100)),
    },
)


def found(result, before: int, after: int, run: int) -> bool:
    return any((m.seed_before, m.seed_after, m.run) == (before, after, run) for m in result.matches)


def straight_end(seed: int, count: int) -> int:
    """The state after ``count`` pulls if none of them repicked (two values each)."""
    for _ in range(2 * count):
        seed = xorshift(seed)

    return seed


def window_with_repick(banner: Banner, start: int, count: int) -> tuple[int, list, int]:
    """Slide along the stream from ``start`` until a ``count``-pull window contains a
    dupe repick (its end state runs one value past the straight window's)."""
    state = start
    for _ in range(20000):
        pulls, end = play(state, banner, count)
        if end != straight_end(state, count):
            return state, pulls, end

        state = xorshift(state)

    raise AssertionError("no repick window found")


def test_play_walks_the_grids_play_chain_including_repicks():
    """play must consume the stream exactly like the byte-validated grid: each pull is
    the cell 1A of its state's grid - or that cell's realized reroll when the previous
    pull dupes it - and leaves the seed where the cell's chain continues."""
    banner = local_banner()
    pulls, end = play(GOLDEN_SEED, banner, 150)

    state, prev, repicks = GOLDEN_SEED, "", 0
    for rarity, slot in pulls:
        rolls = roll_banner(state, banner, 1, last_cat=prev)
        cell = next(p for p in rolls.pulls if (p.position, p.track) == (1, "A"))
        reroll = next(
            (p for p in rolls.rerolls if (p.position, p.track) == (1, "A") and p.realized),
            None,
        )
        got = reroll if reroll is not None else cell
        repicks += reroll is not None

        assert got.cat == banner.pool(rarity)[slot]
        state, prev = got.seed, got.cat

    assert state == end
    assert repicks > 0  # the window must actually exercise the dupe branch


def test_seek_recovers_the_golden_seed_from_eight_pulls():
    banner = local_banner()
    observed, end = play(GOLDEN_SEED, banner, 8)

    result = seek_seed(banner, observed)

    assert not result.truncated
    assert len(result.matches) == 1
    match = result.matches[0]
    assert (match.seed_before, match.seed_after, match.run) == (GOLDEN_SEED, end, 0)


def test_seek_matches_a_window_with_a_repick_inside():
    seed, observed, end = window_with_repick(ALL_RARE, GOLDEN_SEED, 6)

    result = seek_seed(ALL_RARE, observed)

    assert found(result, seed, end, run=0)


def test_seek_reads_a_first_pull_that_was_itself_a_repick():
    """godfat's runs 1/2: when the pull just before the window duped, the window's
    first pull is the repick - seek must still recover the state before the window."""
    start, _, _ = window_with_repick(ALL_RARE, GOLDEN_SEED, 2)
    full, end = play(start, ALL_RARE, 6)
    _, before = play(start, ALL_RARE, 1)  # the window starts at the repicked pull

    result = seek_seed(ALL_RARE, full[1:])

    assert any(
        m.seed_before == before and m.seed_after == end and m.run in (1, 2) for m in result.matches
    )


def test_seek_takes_the_rarity_method_for_a_narrow_first_band():
    state = GOLDEN_SEED
    while play(state, LEGEND_HEAVY, 1)[0][0][0] is not Rarity.LEGEND_RARE:
        state = xorshift(state)
    observed, end = play(state, LEGEND_HEAVY, 6)

    result = seek_seed(LEGEND_HEAVY, observed)

    assert found(result, state, end, run=0)


def test_seek_truncates_an_underdetermined_window():
    result = seek_seed(ALL_RARE, [(Rarity.RARE, 7)], limit=5)

    assert result.truncated
    assert len(result.matches) == 6
    for match in result.matches:
        assert play(match.seed_before, ALL_RARE, 1)[0] == [(Rarity.RARE, 7)]


def test_seek_finds_nothing_for_an_impossible_window():
    # Two consecutive identical rares can't happen: the second would have repicked.
    result = seek_seed(ALL_RARE, [(Rarity.RARE, 5), (Rarity.RARE, 5)])

    assert result.matches == ()
    assert not result.truncated


def test_seek_rejects_bad_observations():
    with pytest.raises(ValueError):
        seek_seed(ALL_RARE, [])
    with pytest.raises(ValueError):
        seek_seed(ALL_RARE, [(Rarity.NORMAL, 0)])
    with pytest.raises(ValueError):
        seek_seed(ALL_RARE, [(Rarity.RARE, 3000)])
    with pytest.raises(ValueError):
        seek_seed(ALL_RARE, [(Rarity.SUPER_RARE, 0)])  # empty pool


def test_seek_reports_monotonic_progress():
    observed, _ = play(GOLDEN_SEED, ALL_RARE, 4)
    fractions = []

    seek_seed(ALL_RARE, observed, progress=lambda run, done: fractions.append((run, done)))

    assert fractions
    assert all(run == 0 for run, _ in fractions)
    assert fractions == sorted(fractions)
    assert fractions[-1][1] == 1.0


# ---- The normal-side gacha through the same sieve ---------------------------------

# Like ALL_RARE: one huge rerolling pool keeps the candidate family tiny, so
# full-space normal seeks run in milliseconds.
NORMAL_WIDE = NormalBanner(
    "wide", "wide test", (NormalPool(10000, tuple(f"I{i}" for i in range(3000)), True),)
)

CATSEYE = BANNERS_BY_KEY["ce"]


def normal_observed(banner: NormalBanner, names: list[str]) -> list[tuple[int, int]]:
    """Item names back to the (pool, slot) pairs seek_normal takes (the banners here
    never repeat a name, so each maps to exactly one slot)."""
    slots = {
        name: (index, slot)
        for index, pool in enumerate(banner.pools)
        for slot, name in enumerate(pool.items)
    }

    return [slots[name] for name in names]


def normal_window_with_repick(banner: NormalBanner, start: int, count: int):
    """normal.play windows until one contains a dupe repick, like window_with_repick."""
    state = start
    for _ in range(20000):
        names, end = normal_play(state, banner, count)
        if end != straight_end(state, count):
            return state, names, end

        state = xorshift(state)

    raise AssertionError("no repick window found")


def test_seek_normal_recovers_a_seed_from_eight_pulls():
    names, end = normal_play(GOLDEN_SEED, NORMAL_WIDE, 8)

    result = seek_normal(NORMAL_WIDE, normal_observed(NORMAL_WIDE, names))

    assert not result.truncated
    assert len(result.matches) == 1
    match = result.matches[0]
    assert (match.seed_before, match.seed_after, match.run) == (GOLDEN_SEED, end, 0)


def test_seek_normal_matches_a_window_with_a_repick_inside():
    seed, names, end = normal_window_with_repick(NORMAL_WIDE, GOLDEN_SEED, 6)

    result = seek_normal(NORMAL_WIDE, normal_observed(NORMAL_WIDE, names))

    assert found(result, seed, end, run=0)


def test_seek_normal_reads_a_first_pull_that_was_itself_a_repick():
    start, _, _ = normal_window_with_repick(NORMAL_WIDE, GOLDEN_SEED, 2)
    full, end = normal_play(start, NORMAL_WIDE, 6)
    _, before = normal_play(start, NORMAL_WIDE, 1)  # the window starts at the repicked pull

    result = seek_normal(NORMAL_WIDE, normal_observed(NORMAL_WIDE, full[1:]))

    assert any(
        m.seed_before == before and m.seed_after == end and m.run in (1, 2) for m in result.matches
    )


def test_seek_normal_on_the_real_catseye_banner():
    """The headline use case: pin the normal seed from Catseye Capsule pulls. A Dark
    Catseye first pull also forces the narrow-band rarity method over a one-item pool.
    Item pools are tiny, so a pull carries far less information than a cat pull -
    12 of them (vs the usual 8) to pin this seed uniquely."""
    state = GOLDEN_SEED
    while normal_play(state, CATSEYE, 1)[0] != ["Dark Catseye"]:
        state = xorshift(state)
    names, end = normal_play(state, CATSEYE, 12)

    result = seek_normal(CATSEYE, normal_observed(CATSEYE, names))

    assert not result.truncated
    assert len(result.matches) == 1
    assert found(result, state, end, run=0)


def test_seek_normal_rejects_bad_observations():
    with pytest.raises(ValueError):
        seek_normal(CATSEYE, [])
    with pytest.raises(ValueError):
        seek_normal(CATSEYE, [(9, 0)])  # no such pool
    with pytest.raises(ValueError):
        seek_normal(CATSEYE, [(4, 1)])  # slot outside the one-item Dark Catseye pool
