from neko.graph import BannerGraph
from neko.models import CATFOOD_PER_DRAW, Path, Rarity, State, TrackPull
from neko.search import Multi, astar, beam_search, obtainable

R = Rarity.RARE
U = Rarity.UBER_SUPER_RARE


def banner(banner_id, *rows):
    return BannerGraph(banner_id, [TrackPull(*row) for row in rows])


def start(position=0, tickets=0, catfood=0, found=()):
    return State(position, tickets, catfood, frozenset(found))


def test_dupe_reroll_target_is_credited():
    g = BannerGraph(
        "x",
        [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Cat", R)],
        rerolls=[TrackPull(2, "A", "Bahamut", R, steps=1)],
    )
    result = astar([g], {"Bahamut"}, start(tickets=2))
    assert result.cats == ("Cat", "Bahamut")


def test_start_dupe_memory_rerolls_the_first_pull():
    g = BannerGraph(
        "x",
        [TrackPull(1, "A", "Cat", R)],
        rerolls=[TrackPull(1, "A", "Bahamut", R, steps=1)],
    )
    plan = astar([g], {"Bahamut"}, State(0, 1, 0, frozenset(), last_cat="Cat"))
    assert plan.cats == ("Bahamut",)


def test_static_dupe_cell_rolls_normally_on_a_clean_arrival():
    g = BannerGraph(
        "x",
        [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Cat", R), TrackPull(3, "A", "Dog", R)],
        rerolls=[TrackPull(2, "A", "Rat", R, steps=1)],
    )
    result = astar([g], {"Cat", "Dog"}, start(position=2, tickets=2))
    assert result.cats == ("Cat", "Dog")


def test_bounce_chain_rerolls_again_on_the_landing():
    g = BannerGraph(
        "x",
        [
            TrackPull(1, "A", "Dog", R),
            TrackPull(2, "A", "Cat", R),
            TrackPull(3, "A", "Cat", R),
            TrackPull(4, "B", "Bird", R),
        ],
        rerolls=[
            TrackPull(3, "A", "Bird", R, steps=1),
            TrackPull(4, "B", "Target", R, steps=1),
        ],
    )
    result = astar([g], {"Target"}, start(tickets=4))
    assert result.cats == ("Dog", "Cat", "Bird", "Target")


def test_guaranteed_multi_started_on_a_dupe_awards_the_duped_column():
    g = BannerGraph(
        "x",
        [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Cat", R), TrackPull(3, "B", "Dog", R)],
        guaranteed=[TrackPull(2, "A", "Filler", U)],
        rerolls=[TrackPull(2, "A", "Rat", R, steps=1)],
        guaranteed_rerolls=[TrackPull(2, "A", "Mekako", U)],
    )
    result = astar([g], {"Mekako"}, start(tickets=1, catfood=2), multis={"x": [Multi(2, 300)]})
    assert result.cats == ("Cat", "Rat", "Mekako")
    assert "guaranteed" in result.legs[-1].kind


def test_no_targets_returns_empty_plan():
    assert astar([banner("x", (1, "A", "Cat", R))], set(), start(tickets=5)) == Path((), 0, 0)


def test_target_on_free_ticket_is_free():
    result = astar([banner("x", (1, "A", "Bahamut", U))], {"Bahamut"}, start(tickets=1))
    assert result.cost == 0


def test_target_paid_with_catfood():
    result = astar([banner("x", (1, "A", "Bahamut", U))], {"Bahamut"}, start(catfood=1))
    assert result.cost == CATFOOD_PER_DRAW


def test_tickets_are_spent_before_catfood():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Dog", R), (3, "A", "Bahamut", U))
    result = astar([g], {"Bahamut"}, start(tickets=2, catfood=5))
    assert result.cost == CATFOOD_PER_DRAW


def test_dear_ticket_is_paid_with_catfood():
    g = banner("x", (1, "A", "Bahamut", U))
    result = astar([g], {"Bahamut"}, start(tickets=1, catfood=1), ticket_value=1000)
    assert result.tickets_used == 0


def test_cheap_ticket_is_still_spent_first():
    g = banner("x", (1, "A", "Bahamut", U))
    result = astar([g], {"Bahamut"}, start(tickets=1, catfood=1), ticket_value=50)
    assert result.tickets_used == 1


def test_unreachable_target_returns_none():
    assert astar([banner("x", (1, "A", "Cat", R))], {"Bahamut"}, start(tickets=5)) is None


def test_obtainable_sees_rolls_rerolls_and_guaranteed():
    g = BannerGraph(
        "x",
        [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Cat", R)],
        guaranteed=[TrackPull(1, "A", "Mecha", U)],
        rerolls=[TrackPull(2, "A", "Bahamut", R, steps=1)],
    )
    assert obtainable([g], {"Cat", "Bahamut", "Mecha", "Ghost"}) == {"Cat", "Bahamut", "Mecha"}


def test_insufficient_resources_returns_none():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Bahamut", U))
    assert astar([g], {"Bahamut"}, start(tickets=1)) is None


def test_picks_the_cheaper_banner():
    x = banner("x", (1, "A", "Bahamut", U))
    y = banner("y", (1, "A", "Cat", R), (2, "A", "Dog", R), (3, "A", "Bahamut", U))
    result = astar([x, y], {"Bahamut"}, start(catfood=5))
    assert result.cost == CATFOOD_PER_DRAW


def test_collects_every_target():
    g = banner("x", (1, "A", "Bahamut", U), (2, "A", "Kasli", U))
    result = astar([g], {"Bahamut", "Kasli"}, start(tickets=2))
    assert set(result.cats) == {"Bahamut", "Kasli"}


def test_follows_a_track_switch_to_reach_target():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Cat", R), (3, "B", "Bahamut", U))
    result = astar([g], {"Bahamut"}, start(tickets=3))
    assert result.cats == ("Cat", "Cat", "Bahamut")


def test_upper_bound_at_optimal_still_finds_plan():
    g = banner("x", (1, "A", "Bahamut", U))
    result = astar([g], {"Bahamut"}, start(catfood=1), upper_bound=CATFOOD_PER_DRAW)
    assert result.cost == CATFOOD_PER_DRAW


def test_upper_bound_below_optimal_returns_none():
    g = banner("x", (1, "A", "Bahamut", U))
    assert astar([g], {"Bahamut"}, start(catfood=1), upper_bound=CATFOOD_PER_DRAW - 1) is None


def test_beam_finds_reachable_target():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Dog", R), (3, "A", "Bahamut", U))
    assert beam_search([g], {"Bahamut"}, start(tickets=3), width=5).cats[-1] == "Bahamut"


def test_beam_matches_astar_with_wide_beam():
    x = banner("x", (1, "A", "Bahamut", U))
    y = banner("y", (1, "A", "Cat", R), (2, "A", "Dog", R), (3, "A", "Bahamut", U))
    s = start(catfood=5)
    assert beam_search([x, y], {"Bahamut"}, s, width=50).cost == astar([x, y], {"Bahamut"}, s).cost


def test_beam_unreachable_returns_none():
    assert beam_search([banner("x", (1, "A", "Cat", R))], {"Bahamut"}, start(tickets=5), 5) is None


def test_beam_collects_multiple_targets():
    g = banner("x", (1, "A", "Bahamut", U), (2, "A", "Kasli", U))
    result = beam_search([g], {"Bahamut", "Kasli"}, start(tickets=2), width=5)
    assert set(result.cats) == {"Bahamut", "Kasli"}


def test_impossible_pair_returns_none_without_exhausting_the_state_space():
    g = banner("x", (1, "A", "Aaa", U), (1, "B", "Bbb", U), (2, "A", "Cat", R), (2, "B", "Dog", R))
    assert astar([g], {"Aaa", "Bbb"}, start(tickets=9)) is None
    assert astar([g], {"Aaa"}, start(tickets=9)) is not None


def guaranteed_banner():
    return BannerGraph(
        "x",
        [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Dog", R)],
        [TrackPull(1, "A", "Mecha", U)],
    )


def test_guaranteed_roll_obtains_the_guaranteed_uber():
    result = astar(
        [guaranteed_banner()], {"Mecha"}, start(catfood=3), multis={"x": [Multi(3, 450)]}
    )
    assert result.cats == ("Cat", "Dog", "Mecha")


def test_guaranteed_roll_costs_the_fixed_price():
    result = astar(
        [guaranteed_banner()], {"Mecha"}, start(catfood=3), multis={"x": [Multi(3, 450)]}
    )
    assert result.cost == 450


def test_guaranteed_unaffordable_returns_none():
    result = astar(
        [guaranteed_banner()], {"Mecha"}, start(catfood=2), multis={"x": [Multi(3, 450)]}
    )
    assert result is None


def test_guaranteed_uber_unreachable_without_config():
    assert astar([guaranteed_banner()], {"Mecha"}, start(catfood=9)) is None


def test_guaranteed_multi_lands_one_step_past_its_final_roll():
    g = BannerGraph(
        "x",
        [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Dog", R), TrackPull(3, "B", "Kasli", U)],
        [TrackPull(1, "A", "Mecha", U)],
    )
    result = astar(
        [g], {"Mecha", "Kasli"}, start(tickets=1, catfood=3), multis={"x": [Multi(3, 450)]}
    )
    assert result.cats == ("Cat", "Dog", "Mecha", "Kasli")
    forced = result.pulls[2]
    assert (forced.guaranteed, forced.position) == (True, 0)


def test_plain_multi_rolls_normal_cats_for_fixed_cost():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Dog", R), (3, "A", "Bahamut", U))
    multi = {"x": [Multi(3, 300, guaranteed=False)]}
    result = astar([g], {"Bahamut"}, start(catfood=3), multis=multi)
    assert (result.cats, result.cost) == (("Cat", "Dog", "Bahamut"), 300)


def test_beam_uses_guaranteed_rolls():
    result = beam_search(
        [guaranteed_banner()], {"Mecha"}, start(catfood=3), 5, multis={"x": [Multi(3, 450)]}
    )
    assert result.cats[-1] == "Mecha"


def test_legs_merge_consecutive_single_pulls():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Dog", R), (3, "A", "Bahamut", U))
    result = astar([g], {"Bahamut"}, start(tickets=3))
    assert [(leg.kind, len(leg.pulls)) for leg in result.legs] == [("Single pull", 3)]


def test_guaranteed_leg_is_labelled_and_separate():
    result = astar(
        [guaranteed_banner()], {"Mecha"}, start(catfood=3), multis={"x": [Multi(3, 450)]}
    )
    assert [(leg.kind, leg.cost) for leg in result.legs] == [("3-roll (guaranteed)", 450)]


def test_banner_limit_zero_excludes_the_banner():
    g = banner("x", (1, "A", "Bahamut", U))
    assert astar([g], {"Bahamut"}, start(tickets=1), banner_limits={"x": 0}) is None


def test_banner_limit_caps_total_pulls():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Bahamut", U))
    assert astar([g], {"Bahamut"}, start(tickets=2), banner_limits={"x": 1}) is None


def test_banner_limit_allows_pulls_up_to_the_cap():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Bahamut", U))
    result = astar([g], {"Bahamut"}, start(tickets=2), banner_limits={"x": 2})
    assert result.cats[-1] == "Bahamut"


def test_banner_limit_routes_around_an_excluded_banner():
    x = banner("x", (1, "A", "Bahamut", U))
    y = banner("y", (1, "A", "Cat", R), (2, "A", "Dog", R), (3, "A", "Bahamut", U))
    result = astar([x, y], {"Bahamut"}, start(tickets=3), banner_limits={"x": 0})
    assert len(result.cats) == 3


def test_banner_limit_blocks_a_too_large_multi():
    result = astar(
        [guaranteed_banner()],
        {"Mecha"},
        start(catfood=3),
        multis={"x": [Multi(3, 450)]},
        banner_limits={"x": 2},
    )
    assert result is None


def test_beam_respects_banner_limit():
    g = banner("x", (1, "A", "Cat", R), (2, "A", "Bahamut", U))
    assert beam_search([g], {"Bahamut"}, start(tickets=2), 5, banner_limits={"x": 1}) is None


def test_prefers_single_banner_when_cost_is_equal():
    x = banner("x", (1, "A", "Aqua", U), (2, "A", "Bora", U))
    y = banner("y", (1, "A", "Aqua", U), (2, "A", "Bora", U))
    result = astar([x, y], {"Aqua", "Bora"}, start(tickets=2))
    assert len(result.legs) == 1
