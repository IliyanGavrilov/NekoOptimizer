from neko.models import Banner, Rarity
from neko.rng import xorshift
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
    # Deleting the only slot leaves nothing to re-pick (godfat's id -1 -> "").
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


def test_pull_seed_is_its_slot_value():
    # Cell j reads the stream at advance^{j+1}(seed) (rarity) and advance^{j+2}(seed)
    # (slot); the state after obtaining a nominal pull is its slot value.
    rolls = roll_banner(42, FOUR_BAND, 2)
    stream = [42]
    for _ in range(5):
        stream.append(xorshift(stream[-1]))
    seeds = {(p.position, p.track): p.seed for p in rolls.pulls}
    assert seeds[(1, "A")] == stream[2]
    assert seeds[(1, "B")] == stream[3]
    assert seeds[(2, "A")] == stream[4]


def test_reseeding_to_a_pull_makes_its_successor_the_new_1a():
    # The apply-plan advance: entering a nominal pull's (after-)seed re-rolls the
    # stream so its play successor (next position, same track) becomes the new 1A.
    rolls = roll_banner(1893568593, FOUR_BAND, 10)
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    duped = {(p.position, p.track) for p in rolls.rerolls}
    checked = 0
    for pull in rolls.pulls:
        successor = (pull.position + 1, pull.track)
        if (pull.position, pull.track) in duped or successor not in nominal:
            continue  # a dupe's after-state is its reroll's, covered below
        assert roll_banner(pull.seed, FOUR_BAND, 1).pulls[0].cat == nominal[successor]
        checked += 1
    assert checked


def test_reseeding_to_a_reroll_continues_past_the_bounce():
    # A dupe's reroll consumed one extra stream value (a two-unit pool always resolves
    # in one step), so its seed re-rolls with the landing cell - half a row on, the
    # other track (index + 3) - as the new 1A.
    rolls = roll_banner(1893568593, TWO_UNIT_RARE, 50)
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    assert rolls.rerolls
    for reroll in rolls.rerolls:
        landing = 2 * (reroll.position - 1) + (0 if reroll.track == "A" else 1) + 3
        successor = (landing // 2 + 1, "AB"[landing % 2])
        if successor not in nominal:
            continue
        assert roll_banner(reroll.seed, TWO_UNIT_RARE, 1).pulls[0].cat == nominal[successor]


def test_seed_before_re_anchors_the_cell_as_the_new_1a():
    # The per-cell dice: entering a pull's seed_before re-rolls the stream so that THIS
    # cell is the new 1A - whatever track it was on (a B cell's chain becomes A's). The
    # anchor is pure stream position, so it holds on every cell, dupes included.
    rolls = roll_banner(1893568593, FOUR_BAND, 10)
    for pull in rolls.pulls:
        assert roll_banner(pull.seed_before, FOUR_BAND, 1).pulls[0].cat == pull.cat


def test_seed_before_of_the_first_cell_is_the_input_seed():
    assert roll_banner(42, FOUR_BAND, 1).pulls[0].seed_before == 42


def test_reseeding_to_a_guaranteed_pull_lands_one_past_the_multi():
    # After a guaranteed multi the play continues half a row on, track flipped: the
    # stored seed (the very value that picked the uber) makes that cell the new 1A.
    rolls = roll_banner(97, ALL_UBER, 30, guaranteed_rolls=11)
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    for pull in rolls.guaranteed[:10]:
        # All-uber rolls never dupe, so the chain's last cell is 10 rows down the same
        # track; the multi continues at the stream index right after it.
        last = 2 * (pull.position - 1) + (0 if pull.track == "A" else 1) + 20
        successor = ((last + 1) // 2 + 1, "AB"[(last + 1) % 2])
        assert roll_banner(pull.seed, ALL_UBER, 1).pulls[0].cat == nominal[successor]


def test_every_named_rare_cell_carries_its_conditional_reroll():
    # Any path can make any rare cell a dupe (a bounce landing or a mid-stream start
    # changes the previously obtained cat), so every named rare cell carries what a
    # dupe there would reroll into, with the extra steps the reroll would consume.
    rolls = roll_banner(1893568593, FOUR_BAND, 50)
    rare = {(p.position, p.track) for p in rolls.pulls if p.rarity is Rarity.RARE and p.cat}
    assert {(r.position, r.track) for r in rolls.rerolls} == rare
    assert all(r.steps >= 1 for r in rolls.rerolls)


def test_realized_rerolls_are_the_straight_chain_dupes_and_their_bounces():
    # godfat renders an R cell exactly where a straight chain hits a dupe: a cell that
    # repeats its same-track predecessor, or the landing of a realized reroll that
    # repeats the rerolled cat (a bounce, which rerolls again). Everything else stays
    # a conditional cell other paths can trigger.
    rolls = roll_banner(1893568593, TWO_UNIT_RARE, 300)
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    static = {
        (pos, track)
        for (pos, track), cat in nominal.items()
        if nominal.get((pos - 1, track)) == cat
    }
    rerolls = {(r.position, r.track): r for r in rolls.rerolls}
    realized = {spot for spot, reroll in rerolls.items() if reroll.realized}
    assert static <= realized
    bounces = realized - static
    assert bounces  # this seed does bounce
    for pos, track in bounces:
        index = 2 * (pos - 1) + (track == "B")
        # some realized reroll lands exactly here holding this cell's nominal cat
        assert any(
            reroll.realized
            and 2 * (p - 1) + (t == "B") + 2 + reroll.steps == index
            and reroll.cat == nominal[(pos, track)]
            for (p, t), reroll in rerolls.items()
        )


def test_guaranteed_reroll_column_diverges_where_the_chains_do():
    # A multi started on a dupe walks the reroll's chain (an extra step from the very
    # first roll), so its final cell - and the awarded uber - can differ from a clean
    # start's. The duped column covers every reroll cell rolled with a guarantee.
    dupey = banner(
        {Rarity.RARE: 9000, Rarity.UBER_SUPER_RARE: 1000},
        {
            Rarity.RARE: ("R1", "R2"),
            Rarity.UBER_SUPER_RARE: ("U1", "U2", "U3", "U4", "U5"),
        },
    )
    rolls = roll_banner(1893568593, dupey, 100, guaranteed_rolls=11)
    spots = {(r.position, r.track) for r in rolls.rerolls}
    assert {(g.position, g.track) for g in rolls.guaranteed_rerolls} == spots
    clean = {(g.position, g.track): g.cat for g in rolls.guaranteed}
    assert any(g.cat != clean[(g.position, g.track)] for g in rolls.guaranteed_rerolls)


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
