from neko.models import Banner, Rarity
from neko.roll import pick_rarity, roll_banner


def banner(rates, pools) -> Banner:
    return Banner("test", "Test Banner", "", rates, pools)


# A realistic-ish four-band split (sums to 10000) for the rarity walk.
FOUR_BAND = banner(
    {
        Rarity.RARE: 6970,
        Rarity.SUPER_RARE: 2510,
        Rarity.UBER_SUPER_RARE: 490,
        Rarity.LEGEND_RARE: 30,
    },
    {
        Rarity.RARE: ("R1", "R2", "R3"),
        Rarity.SUPER_RARE: ("S1", "S2"),
        Rarity.UBER_SUPER_RARE: ("U1",),
        Rarity.LEGEND_RARE: ("L1",),
    },
)
TWO_UNIT_RARE = banner({Rarity.RARE: 10000}, {Rarity.RARE: ("R1", "R2")})
ONE_UNIT_RARE = banner({Rarity.RARE: 10000}, {Rarity.RARE: ("Only",)})


def test_pick_rarity_walks_cumulative_bands():
    b = FOUR_BAND  # cumulative edges: 6970 / 9480 / 9970
    assert pick_rarity(0, b) is Rarity.RARE
    assert pick_rarity(6969, b) is Rarity.RARE
    assert pick_rarity(6970, b) is Rarity.SUPER_RARE
    assert pick_rarity(9479, b) is Rarity.SUPER_RARE
    assert pick_rarity(9480, b) is Rarity.UBER_SUPER_RARE
    assert pick_rarity(9969, b) is Rarity.UBER_SUPER_RARE


def test_pick_rarity_legend_is_the_catch_all():
    # Everything past Uber's cumulative rate is Legend, even beyond the summed rates.
    assert pick_rarity(9970, FOUR_BAND) is Rarity.LEGEND_RARE
    assert pick_rarity(9999, FOUR_BAND) is Rarity.LEGEND_RARE


def test_every_position_yields_both_tracks():
    rolls = roll_banner(1893568593, FOUR_BAND, 20)
    assert len(rolls.pulls) == 40
    assert {(p.position, p.track) for p in rolls.pulls} == {
        (pos, track) for pos in range(1, 21) for track in ("A", "B")
    }


def test_cats_come_from_their_rarity_pool():
    for pull in roll_banner(1893568593, FOUR_BAND, 200).pulls:
        assert pull.cat in FOUR_BAND.pool(pull.rarity)


def test_rare_dupe_rerolls_to_the_other_unit():
    # With a two-unit rare pool, a dupe deletes that slot and the shrunk pool has exactly
    # one unit left, so the reroll is deterministically the OTHER unit.
    rolls = roll_banner(1893568593, TWO_UNIT_RARE, 300)
    assert rolls.rerolls  # dupes do occur over 300 positions
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    for reroll in rolls.rerolls:
        other = "R2" if nominal[(reroll.position, reroll.track)] == "R1" else "R1"
        assert reroll.cat == other and reroll.rarity is Rarity.RARE


def test_reroll_on_a_single_unit_pool_empties():
    # Deleting the only slot leaves nothing to re-pick (godfat's id -1 → "").
    rolls = roll_banner(1893568593, ONE_UNIT_RARE, 10)
    assert rolls.rerolls and all(r.cat == "" for r in rolls.rerolls)


def test_deterministic():
    a = roll_banner(42, FOUR_BAND, 50)
    b = roll_banner(42, FOUR_BAND, 50)
    assert a.pulls == b.pulls and a.rerolls == b.rerolls


def test_no_guaranteed_column_without_a_roll_count():
    assert roll_banner(42, FOUR_BAND, 50).guaranteed == []


def test_guaranteed_column_is_an_uber_at_every_cell():
    # An 11-roll guaranteed started at any cell awards an uber. We roll a buffer past the
    # display so the forward follow always resolves (godfat drops trailing cells only
    # because it has no data past its window; the RNG past it is still deterministic).
    rolls = roll_banner(1893568593, FOUR_BAND, 40, guaranteed_rolls=11)
    assert len(rolls.guaranteed) == 40 * 2
    assert {(p.position, p.track) for p in rolls.guaranteed} == {
        (pos, track) for pos in range(1, 41) for track in ("A", "B")
    }
    for pull in rolls.guaranteed:
        assert pull.rarity is Rarity.UBER_SUPER_RARE
        assert pull.cat in FOUR_BAND.pool(Rarity.UBER_SUPER_RARE)


ALL_UBER = banner(
    {Rarity.RARE: 0, Rarity.SUPER_RARE: 0, Rarity.UBER_SUPER_RARE: 10000},
    {Rarity.UBER_SUPER_RARE: ("U1", "U2", "U3", "U4", "U5", "U6", "U7")},
)


def test_guaranteed_follows_the_play_chain():
    # godfat's fill_guaranteed: the column value at a cell is the uber picked by the
    # rarity seed of the cell guaranteed_rolls - 1 chain steps FORWARD (the swapped final
    # roll). With every roll an uber there are no rare dupes, so the chain never switches
    # tracks and an 11-roll column must equal the 1-roll column (godfat's
    # force_guaranteed=1, a 0-step follow) shifted 10 rows down the same track.
    eleven = roll_banner(97, ALL_UBER, 30, guaranteed_rolls=11)
    one = roll_banner(97, ALL_UBER, 45, guaranteed_rolls=1)
    single = {(p.position, p.track): p.cat for p in one.guaranteed}
    assert eleven.guaranteed
    for pull in eleven.guaranteed:
        assert pull.cat == single[(pull.position + 10, pull.track)]


def test_guaranteed_chain_crosses_tracks_on_a_dupe():
    # With rare dupes in play the chain switches tracks mid-follow, so the 11-roll column
    # cannot be a plain same-track shift of the 1-roll column.
    dupey = banner(
        {Rarity.RARE: 9000, Rarity.UBER_SUPER_RARE: 1000},
        {
            Rarity.RARE: ("R1", "R2"),
            Rarity.UBER_SUPER_RARE: ("U1", "U2", "U3", "U4", "U5"),
        },
    )
    rolls = roll_banner(1893568593, dupey, 100, guaranteed_rolls=11)
    assert rolls.rerolls  # dupes (and thus track switches) do occur on this seed
    one = roll_banner(1893568593, dupey, 130, guaranteed_rolls=1)
    single = {(p.position, p.track): p.cat for p in one.guaranteed}
    assert any(pull.cat != single[(pull.position + 10, pull.track)] for pull in rolls.guaranteed)
