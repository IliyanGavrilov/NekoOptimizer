import pytest

from neko.graph import BannerGraph, Outcome, build_graphs, stream_index
from neko.models import Rarity, TrackPull

R = Rarity.RARE
S = Rarity.SUPER_RARE
U = Rarity.UBER_SUPER_RARE


def graph(*rows):
    return BannerGraph("b", [TrackPull(*row) for row in rows])


@pytest.mark.parametrize(
    "position,track,index",
    [(1, "A", 0), (1, "B", 1), (2, "A", 2), (2, "B", 3), (3, "A", 4)],
)
def test_stream_index(position, track, index):
    assert stream_index(position, track) == index


def test_normal_pull_advances_two_positions():
    assert graph((1, "A", "Cat", R), (2, "A", "Dog", R)).outcome(0) == Outcome("Cat", R, 2, False)


def test_consecutive_rare_dupe_switches_track():
    assert graph((1, "A", "Cat", R), (2, "A", "Cat", R)).outcome(2) == Outcome("Cat", R, 5, True)


def test_duplicate_non_rare_does_not_switch():
    assert graph((1, "A", "Hero", U), (2, "A", "Hero", U)).outcome(2) == Outcome(
        "Hero", U, 4, False
    )


def test_rare_dupe_uses_the_rerolled_cat():
    g = BannerGraph(
        "b",
        [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Cat", R)],
        rerolls=[TrackPull(2, "A", "Dog", R)],
    )
    assert g.outcome(2) == Outcome("Dog", R, 5, True)


def test_build_graphs_wires_rerolls():
    graphs = build_graphs(
        {"x": [TrackPull(1, "A", "Cat", R), TrackPull(2, "A", "Cat", R)]},
        rerolls={"x": [TrackPull(2, "A", "Dog", R)]},
    )
    assert graphs[0].outcome(2).cat == "Dog"


def test_outcome_missing_position_is_none():
    assert graph((1, "A", "Cat", R)).outcome(99) is None


def test_positions_are_sorted_indices():
    assert graph((2, "A", "Dog", R), (1, "A", "Cat", R)).positions() == [0, 2]


def test_build_graphs_keeps_banner_ids():
    graphs = build_graphs({"x": [TrackPull(1, "A", "Cat", R)], "y": []})
    assert [g.banner_id for g in graphs] == ["x", "y"]


def test_guaranteed_keeps_cat_and_advances_one():
    g = BannerGraph("b", [], [TrackPull(1, "A", "Bahamut", U)])
    assert g.guaranteed(0) == Outcome("Bahamut", U, 1, False)


def test_guaranteed_missing_position_is_none():
    assert graph((1, "A", "Cat", R)).guaranteed(0) is None


def test_build_graphs_wires_guaranteed_pulls():
    graphs = build_graphs({"x": []}, {"x": [TrackPull(1, "A", "Bahamut", U)]})
    assert graphs[0].guaranteed(0) == Outcome("Bahamut", U, 1, False)


def test_outcome_carries_the_pull_seed():
    assert graph((1, "A", "Cat", R, 111)).outcome(0).seed == 111


def test_dupe_outcome_carries_the_reroll_seed():
    g = BannerGraph(
        "b",
        [TrackPull(1, "A", "Cat", R, seed=111), TrackPull(2, "A", "Cat", R, seed=222)],
        rerolls=[TrackPull(2, "A", "Dog", R, seed=333)],
    )
    assert g.outcome(2).seed == 333


def test_guaranteed_outcome_carries_the_pull_seed():
    g = BannerGraph("b", [], [TrackPull(1, "A", "Bahamut", U, seed=444)])
    assert g.guaranteed(0).seed == 444


def test_resolve_rerolls_only_when_the_last_cat_repeats():
    g = BannerGraph(
        "b",
        [TrackPull(1, "A", "Ape", U), TrackPull(2, "A", "Cat", R, seed=8)],
        rerolls=[TrackPull(2, "A", "Dog", R, seed=9, steps=1)],
    )
    assert g.resolve(2, "Cat") == Outcome("Dog", R, 5, True, 9)
    assert g.resolve(2, "Ape") == Outcome("Cat", R, 4, False, 8)
    assert g.resolve(2) == Outcome("Cat", R, 4, False, 8)


def test_resolve_multi_step_reroll_advances_further():
    g = BannerGraph(
        "b",
        [TrackPull(1, "A", "Cat", R)],
        rerolls=[TrackPull(1, "A", "Dog", R, steps=2)],
    )
    assert g.resolve(0, "Cat").next_position == 4


def test_static_outcome_is_resolve_against_the_same_track_predecessor():
    g = graph((1, "A", "Cat", R), (2, "A", "Cat", R), (2, "B", "Cat", R))
    assert g.outcome(2).switched is True
    assert g.outcome(3).switched is False
    assert g.resolve(2, "Cat") == g.outcome(2)


def test_reroll_and_realized_expose_the_conditional_cell():
    g = BannerGraph(
        "b",
        [TrackPull(1, "A", "Ape", U), TrackPull(2, "A", "Cat", R)],
        rerolls=[TrackPull(2, "A", "Dog", R, seed=9, steps=1, realized=True)],
    )
    assert g.reroll(2) == Outcome("Dog", R, 5, True, 9)
    assert g.realized(2) is True
    assert g.reroll(0) is None and g.realized(0) is False


def test_guaranteed_duped_reads_the_reroll_column():
    g = BannerGraph(
        "b",
        [TrackPull(1, "A", "Cat", R)],
        guaranteed=[TrackPull(1, "A", "Bahamut", U, seed=5)],
        guaranteed_rerolls=[TrackPull(1, "A", "Mekako", U, seed=6)],
    )
    assert g.guaranteed(0) == Outcome("Bahamut", U, 1, False, 5)
    assert g.guaranteed(0, duped=True) == Outcome("Mekako", U, 1, False, 6)
    assert g.guaranteed_positions(duped=True) == [0]


def test_build_graphs_wires_guaranteed_rerolls():
    graphs = build_graphs(
        {"x": [TrackPull(1, "A", "Cat", R)]},
        guaranteed_rerolls={"x": [TrackPull(1, "A", "Mekako", U)]},
    )
    assert graphs[0].guaranteed(0, duped=True).cat == "Mekako"


def test_max_advance_tracks_the_worst_reroll():
    plain = graph((1, "A", "Cat", R))
    assert plain.max_advance() == 3
    g = BannerGraph(
        "b",
        [TrackPull(1, "A", "Cat", R)],
        rerolls=[TrackPull(1, "A", "Dog", R, steps=2)],
    )
    assert g.max_advance() == 4
