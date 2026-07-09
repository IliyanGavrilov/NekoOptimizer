from neko.models import Banner, Rarity
from neko.rng import xorshift
from neko.roll import pick_rarity, roll_banner


def banner(rates, pools) -> Banner:
    return Banner("test", "Test Banner", "", rates, pools)


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
    b = FOUR_BAND
    assert pick_rarity(0, b) is Rarity.RARE
    assert pick_rarity(6969, b) is Rarity.RARE
    assert pick_rarity(6970, b) is Rarity.SUPER_RARE
    assert pick_rarity(9479, b) is Rarity.SUPER_RARE
    assert pick_rarity(9480, b) is Rarity.UBER_SUPER_RARE
    assert pick_rarity(9969, b) is Rarity.UBER_SUPER_RARE


def test_pick_rarity_legend_is_the_catch_all():
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
    rolls = roll_banner(1893568593, TWO_UNIT_RARE, 300)
    assert rolls.rerolls
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    for reroll in rolls.rerolls:
        other = "R2" if nominal[(reroll.position, reroll.track)] == "R1" else "R1"
        assert reroll.cat == other and reroll.rarity is Rarity.RARE


def test_reroll_on_a_single_unit_pool_empties():
    rolls = roll_banner(1893568593, ONE_UNIT_RARE, 10)
    assert rolls.rerolls and all(r.cat == "" for r in rolls.rerolls)


def test_deterministic():
    a = roll_banner(42, FOUR_BAND, 50)
    b = roll_banner(42, FOUR_BAND, 50)
    assert a.pulls == b.pulls and a.rerolls == b.rerolls


def test_last_cat_dupes_the_first_cell():
    def reroll_at_1a(rolls):
        return next(r for r in rolls.rerolls if (r.position, r.track) == (1, "A"))

    clean = roll_banner(42, TWO_UNIT_RARE, 5)
    first = next(p for p in clean.pulls if (p.position, p.track) == (1, "A"))
    assert not reroll_at_1a(clean).realized
    duped = roll_banner(42, TWO_UNIT_RARE, 5, last_cat=first.cat)
    assert reroll_at_1a(duped).realized


def test_last_cat_not_repeated_changes_nothing():
    a = roll_banner(42, TWO_UNIT_RARE, 5, last_cat="Some Other Cat")
    b = roll_banner(42, TWO_UNIT_RARE, 5)
    assert a.pulls == b.pulls and a.rerolls == b.rerolls


def test_no_guaranteed_column_without_a_roll_count():
    assert roll_banner(42, FOUR_BAND, 50).guaranteed == []


def test_roll_banner_records_the_guaranteed_multi_length():
    assert roll_banner(42, FOUR_BAND, 10).guaranteed_rolls == 0
    assert roll_banner(42, FOUR_BAND, 10, guaranteed_rolls=11).guaranteed_rolls == 11


def test_guaranteed_column_is_an_uber_at_every_cell():
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
    eleven = roll_banner(97, ALL_UBER, 30, guaranteed_rolls=11)
    one = roll_banner(97, ALL_UBER, 45, guaranteed_rolls=1)
    single = {(p.position, p.track): p.cat for p in one.guaranteed}
    assert eleven.guaranteed
    for pull in eleven.guaranteed:
        assert pull.cat == single[(pull.position + 10, pull.track)]


def test_pull_seed_is_its_slot_value():
    rolls = roll_banner(42, FOUR_BAND, 2)
    stream = [42]
    for _ in range(5):
        stream.append(xorshift(stream[-1]))
    seeds = {(p.position, p.track): p.seed for p in rolls.pulls}
    assert seeds[(1, "A")] == stream[2]
    assert seeds[(1, "B")] == stream[3]
    assert seeds[(2, "A")] == stream[4]


def test_pull_carries_the_rarity_seed_one_step_before_its_slot_seed():
    rolls = roll_banner(42, FOUR_BAND, 2)
    stream = [42]
    for _ in range(5):
        stream.append(xorshift(stream[-1]))
    rarity_seeds = {(p.position, p.track): p.rarity_seed for p in rolls.pulls}
    assert rarity_seeds[(1, "A")] == stream[1]
    assert rarity_seeds[(1, "B")] == stream[2]
    # The rarity seed is exactly the slot seed's predecessor in the stream.
    assert all(xorshift(p.rarity_seed) == p.seed for p in rolls.pulls)


def test_reseeding_to_a_pull_makes_its_successor_the_new_1a():
    rolls = roll_banner(1893568593, FOUR_BAND, 10)
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    duped = {(p.position, p.track) for p in rolls.rerolls}
    checked = 0
    for pull in rolls.pulls:
        successor = (pull.position + 1, pull.track)
        if (pull.position, pull.track) in duped or successor not in nominal:
            continue
        assert roll_banner(pull.seed, FOUR_BAND, 1).pulls[0].cat == nominal[successor]
        checked += 1
    assert checked


def test_reseeding_to_a_reroll_continues_past_the_bounce():
    rolls = roll_banner(1893568593, TWO_UNIT_RARE, 50)
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    assert rolls.rerolls
    for reroll in rolls.rerolls:
        landing = 2 * (reroll.position - 1) + (0 if reroll.track == "A" else 1) + 3
        successor = (landing // 2 + 1, "AB"[landing % 2])
        if successor not in nominal:
            continue
        assert roll_banner(reroll.seed, TWO_UNIT_RARE, 1).pulls[0].cat == nominal[successor]


def test_reseeding_to_a_guaranteed_pull_lands_one_past_the_multi():
    rolls = roll_banner(97, ALL_UBER, 30, guaranteed_rolls=11)
    nominal = {(p.position, p.track): p.cat for p in rolls.pulls}
    for pull in rolls.guaranteed[:10]:
        last = 2 * (pull.position - 1) + (0 if pull.track == "A" else 1) + 20
        successor = ((last + 1) // 2 + 1, "AB"[(last + 1) % 2])
        assert roll_banner(pull.seed, ALL_UBER, 1).pulls[0].cat == nominal[successor]


def test_every_named_rare_cell_carries_its_conditional_reroll():
    rolls = roll_banner(1893568593, FOUR_BAND, 50)
    rare = {(p.position, p.track) for p in rolls.pulls if p.rarity is Rarity.RARE and p.cat}
    assert {(r.position, r.track) for r in rolls.rerolls} == rare
    assert all(r.steps >= 1 for r in rolls.rerolls)


def test_realized_rerolls_are_the_straight_chain_dupes_and_their_bounces():
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
    assert bounces
    for pos, track in bounces:
        index = 2 * (pos - 1) + (track == "B")
        assert any(
            reroll.realized
            and 2 * (p - 1) + (t == "B") + 2 + reroll.steps == index
            and reroll.cat == nominal[(pos, track)]
            for (p, t), reroll in rerolls.items()
        )


def test_guaranteed_reroll_column_diverges_where_the_chains_do():
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
    dupey = banner(
        {Rarity.RARE: 9000, Rarity.UBER_SUPER_RARE: 1000},
        {
            Rarity.RARE: ("R1", "R2"),
            Rarity.UBER_SUPER_RARE: ("U1", "U2", "U3", "U4", "U5"),
        },
    )
    rolls = roll_banner(1893568593, dupey, 100, guaranteed_rolls=11)
    assert rolls.rerolls
    one = roll_banner(1893568593, dupey, 130, guaranteed_rolls=1)
    single = {(p.position, p.track): p.cat for p in one.guaranteed}
    assert any(pull.cat != single[(pull.position + 10, pull.track)] for pull in rolls.guaranteed)
