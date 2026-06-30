from datetime import date, timedelta

import pytest

from neko.godfat import BannerRolls, TrackPull
from neko.graph import stream_index
from neko.models import Leg, Path, Pull, Rarity
from neko.subsets import SubsetPlan
from planner.models import Banner, Cat
from planner.services import (
    capped_banner_limits,
    catalogue,
    cost_label,
    dated_catalogue,
    equivalent_banners,
    plan_views,
    track_rows,
)


def test_capped_banner_limits_matches_only_platinum_and_legend():
    names = ["Platinum Capsules", "Legend Capsules", "Epicfest"]
    assert capped_banner_limits(names, 0) == {"Platinum Capsules": 0, "Legend Capsules": 0}


@pytest.mark.django_db
def test_catalogue_nests_rarity_under_banner():
    cat = Cat.objects.create(name="Bahamut", rarity="Uber Super Rare")
    cat.banners.add(Banner.objects.create(name="Epicfest"))
    assert catalogue([cat]) == [("Epicfest", [("Uber Super Rare", [cat])])]


@pytest.mark.django_db
def test_catalogue_files_bannerless_cat_under_other():
    cat = Cat.objects.create(name="Bahamut")
    assert catalogue([cat]) == [("Other", [("Unknown", [cat])])]


@pytest.mark.django_db
def test_catalogue_lists_cat_in_every_banner():
    cat = Cat.objects.create(name="Bahamut")
    cat.banners.add(Banner.objects.create(name="Epicfest"), Banner.objects.create(name="Uberfest"))
    assert [banner for banner, _ in catalogue([cat])] == ["Epicfest", "Uberfest"]


@pytest.mark.django_db
def test_catalogue_orders_rarities_cheapest_to_rarest():
    banner = Banner.objects.create(name="Uberfest")
    legend = Cat.objects.create(name="Mecha", rarity="Legend Rare")
    rare = Cat.objects.create(name="Pogo", rarity="Rare")
    legend.banners.add(banner)
    rare.banners.add(banner)
    rarities = [rarity for rarity, _ in catalogue([legend, rare])[0][1]]
    assert rarities == ["Rare", "Legend Rare"]


@pytest.mark.django_db
def test_catalogue_reverse_rarity_lists_rarest_first():
    banner = Banner.objects.create(name="Uberfest")
    legend = Cat.objects.create(name="Mecha", rarity="Legend Rare")
    rare = Cat.objects.create(name="Pogo", rarity="Rare")
    legend.banners.add(banner)
    rare.banners.add(banner)
    rarities = [rarity for rarity, _ in catalogue([legend, rare], reverse_rarity=True)[0][1]]
    assert rarities == ["Legend Rare", "Rare"]


def _dated_banner(name, start, end):
    banner = Banner.objects.create(name=name, start=start, end=end)
    cat = Cat.objects.create(name=f"{name} cat")
    cat.banners.add(banner)
    return cat


@pytest.mark.django_db
def test_dated_catalogue_splits_now_upcoming_and_past():
    today = date(2026, 6, 15)
    day = timedelta(days=1)
    _dated_banner("Soon", today + 5 * day, today + 10 * day)
    _dated_banner("Later", today + 20 * day, today + 25 * day)
    _dated_banner("ActiveNow", today - day, today + day)
    _dated_banner("OldPast", today - 30 * day, today - 20 * day)
    _dated_banner("RecentPast", today - 6 * day, today - 2 * day)

    groups = dated_catalogue(Cat.objects.all(), today=today)
    labelled = {label: [name for name, _dates, _ in sections] for label, sections in groups}
    assert labelled["Available now"] == ["ActiveNow"]
    assert labelled["Upcoming"] == ["Soon", "Later"]
    assert labelled["Past"] == ["RecentPast", "OldPast"]


@pytest.mark.django_db
def test_dated_catalogue_carries_banner_dates():
    today = date(2026, 6, 15)
    run = (today, today + timedelta(days=3))
    banner = Banner.objects.create(name="ActiveNow", start=run[0], end=run[1])
    Cat.objects.create(name="Cat").banners.add(banner)
    _label, sections = dated_catalogue(Cat.objects.all(), today=today)[0]
    assert sections[0][1] == run


def test_equivalent_banners_groups_identical_roll_sequences():
    same = [TrackPull(1, "A", "Bahamut", Rarity.UBER_SUPER_RARE)]
    other = [TrackPull(1, "A", "Kasli", Rarity.UBER_SUPER_RARE)]
    banners = {
        "A": BannerRolls(same, []),
        "B": BannerRolls(same, []),
        "C": BannerRolls(other, []),
    }
    equivalent = equivalent_banners(banners)
    assert sorted(equivalent["A"]) == ["A", "B"]
    assert equivalent["C"] == ["C"]


def _grid(*track_pulls):
    return {stream_index(p.position, p.track): p for p in track_pulls}


def test_track_rows_window_spans_only_the_positions_the_path_touches():
    grid = _grid(
        TrackPull(1, "A", "A1", Rarity.RARE),
        TrackPull(2, "A", "A2", Rarity.SUPER_RARE),
        TrackPull(3, "A", "A3", Rarity.RARE),
    )
    pulls = [Pull(0, "bn", "A1", Rarity.RARE), Pull(2, "bn", "A2", Rarity.SUPER_RARE)]
    assert [row["pos"] for row in track_rows(pulls, grid, set(), set())] == [1, 2]


def test_track_rows_marks_path_cells_on_their_track():
    grid = _grid(TrackPull(1, "A", "A1", Rarity.RARE), TrackPull(1, "B", "B1", Rarity.RARE))
    rows = track_rows([Pull(0, "bn", "A1", Rarity.RARE)], grid, set(), set())
    assert (rows[0]["a"]["on_path"], rows[0]["b"]["on_path"]) == (True, False)


def test_track_rows_flags_a_track_switch_on_the_landing_cell():
    grid = _grid(
        TrackPull(1, "A", "A1", Rarity.RARE), TrackPull(2, "B", "B2", Rarity.UBER_SUPER_RARE)
    )
    # 1A (index 0, even) -> 2B (index 3, odd): the track flips, so 2B is a switch.
    pulls = [Pull(0, "bn", "A1", Rarity.RARE), Pull(3, "bn", "B2", Rarity.UBER_SUPER_RARE)]
    assert track_rows(pulls, grid, set(), set())[1]["b"]["switch"] is True


def test_track_rows_marks_target_cats():
    grid = _grid(TrackPull(1, "A", "Bahamut", Rarity.UBER_SUPER_RARE))
    rows = track_rows([Pull(0, "bn", "Bahamut", Rarity.UBER_SUPER_RARE)], grid, {"Bahamut"}, set())
    assert rows[0]["a"]["target"] is True


def test_track_rows_marks_unowned_path_cats():
    grid = _grid(TrackPull(1, "A", "Bahamut", Rarity.UBER_SUPER_RARE))
    rows = track_rows([Pull(0, "bn", "Bahamut", Rarity.UBER_SUPER_RARE)], grid, set(), {"Kasli"})
    assert rows[0]["a"]["unowned"] is True


def test_track_rows_yields_none_for_an_empty_off_path_slot():
    grid = _grid(TrackPull(1, "A", "A1", Rarity.RARE))  # no 1B cell
    rows = track_rows([Pull(0, "bn", "A1", Rarity.RARE)], grid, set(), set())
    assert rows[0]["b"] is None


@pytest.mark.parametrize(
    "tickets,catfood,expected",
    [
        (11, 0, "11 tickets"),
        (1, 0, "1 ticket"),
        (0, 1500, "1500 catfood"),
        (1, 900, "1 ticket + 900 catfood"),
        (0, 0, "free"),
    ],
)
def test_cost_label_spells_out_both_currencies(tickets, catfood, expected):
    assert cost_label(tickets, catfood) == expected


def test_plan_views_flags_the_first_leg_of_each_banner():
    def leg(banner, kind):
        return Leg(banner, kind, 0, (Pull(0, banner, "Cat", Rarity.RARE),))

    # Two Y legs of different kinds stay separate (Path.legs only merges single pulls).
    moves = (leg("X", "Single pull"), leg("Y", "11-roll"), leg("Y", "Single pull"))
    path = Path(moves[0].pulls, tickets_used=3, catfood_draws_used=0, moves=moves)
    option = SubsetPlan(frozenset({"Cat"}), path)
    grids = {
        "X": [TrackPull(1, "A", "Cat", Rarity.RARE)],
        "Y": [TrackPull(1, "A", "Cat", Rarity.RARE)],
    }
    views = plan_views([option], grids, {"X": ["X"], "Y": ["Y"]}, set())
    assert [seg["new_banner"] for seg in views[0]["segments"]] == [True, True, False]
