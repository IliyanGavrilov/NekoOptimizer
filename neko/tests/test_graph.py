import pytest

from neko.godfat import TrackPull
from neko.graph import BannerGraph, Outcome, build_graphs, stream_index
from neko.models import Rarity

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
