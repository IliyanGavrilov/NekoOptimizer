from datetime import date, timedelta

import pytest

from neko.godfat import BannerRolls, TrackPull
from neko.models import Leg, Path, Pull, Rarity
from neko.subsets import SubsetPlan
from planner.models import Banner, Cat
from planner.services import (
    build_tracks,
    capped_banner_limits,
    catalogue,
    cost_label,
    dated_catalogue,
    equivalent_banners,
    picker_groups,
    plan_highlight,
    plan_summary,
)

U = Rarity.UBER_SUPER_RARE
R = Rarity.RARE


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


def _run(start, end, pool_id, name):
    from neko.gachadata import GachaEventRow

    return GachaEventRow(
        f"{start}_{pool_id}", name, start, end, pool_id, 7000, 2500, 500, 0, False, False
    )


@pytest.mark.django_db
def test_picker_groups_lists_each_scheduled_run_separately():
    # A recurring name (Platinum Capsules) gets one row per run: the current run's 2030
    # sentinel end is capped by its July rerun, and the rerun shows under Upcoming.
    today = date(2026, 7, 3)
    sentinel = date(2030, 1, 1)
    events = [
        _run(date(2026, 4, 24), sentinel, 1, "Platinum"),
        _run(date(2026, 7, 11), sentinel, 2, "Platinum"),
        _run(date(2026, 6, 26), date(2026, 7, 3), 3, "Trixi"),
    ]
    cat = Cat.objects.create(name="Luno", rarity="Uber Super Rare")
    cat.banners.add(Banner.objects.create(name="Platinum"))
    groups = dict(picker_groups(Cat.objects.all(), today=today, events=events))
    now = [(name, dates) for name, dates, _ in groups["Available now"]]
    assert now == [
        ("Platinum", (date(2026, 4, 24), date(2026, 7, 10))),
        ("Trixi", (date(2026, 6, 26), date(2026, 7, 3))),
    ]
    upcoming = [(n, d) for n, d, _ in groups["Upcoming"]]
    assert upcoming == [("Platinum", (date(2026, 7, 11), sentinel))]
    # both Platinum rows carry the same cats, joined by name
    assert groups["Available now"][0][2] == [("Uber Super Rare", [cat])]
    assert groups["Upcoming"][0][2] == [("Uber Super Rare", [cat])]


@pytest.mark.django_db
def test_picker_groups_keeps_unscheduled_past_banners_db_dated():
    today = date(2026, 7, 3)
    _dated_banner("OldFest", date(2026, 5, 1), date(2026, 5, 4))
    groups = dict(picker_groups(Cat.objects.all(), today=today, events=[]))
    assert [(n, d) for n, d, _ in groups["Past"]] == [
        ("OldFest", (date(2026, 5, 1), date(2026, 5, 4)))
    ]


@pytest.mark.django_db
def test_picker_groups_lists_every_past_rerun_with_cats_on_the_newest():
    today = date(2026, 7, 3)
    events = [
        _run(date(2026, 2, 1), date(2026, 2, 5), 1, "Fest"),
        _run(date(2026, 5, 1), date(2026, 5, 5), 2, "Fest"),
    ]
    cat = Cat.objects.create(name="Bahamut", rarity="Uber Super Rare")
    cat.banners.add(Banner.objects.create(name="Fest"))
    groups = dict(picker_groups(Cat.objects.all(), today=today, events=events))
    assert [(n, d) for n, d, _ in groups["Past"]] == [
        ("Fest", (date(2026, 5, 1), date(2026, 5, 5))),
        ("Fest", (date(2026, 2, 1), date(2026, 2, 5))),
    ]
    newest, oldest = groups["Past"]
    assert newest[2] == [("Uber Super Rare", [cat])]
    assert oldest[2] == []


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


def test_build_tracks_merges_equivalent_banners_into_one_legend_entry():
    pulls = [TrackPull(1, "A", "Bahamut", U)]
    track = build_tracks({"X": pulls, "Y": pulls}, {}, {"X": ["X", "Y"], "Y": ["X", "Y"]})
    assert len(track["legend"]) == 1


def test_build_tracks_stacks_each_banners_cat_in_one_cell():
    banner_pulls = {
        "X": [TrackPull(1, "A", "Bahamut", U)],
        "Y": [TrackPull(1, "A", "Kasli", U)],
    }
    cell = build_tracks(banner_pulls, {}, {})["rows"][0]["a"]
    assert [e["cat"] for e in cell] == ["Bahamut", "Kasli"]


def test_build_tracks_places_each_roll_on_its_track():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U), TrackPull(1, "B", "Kasli", U)]}
    row = build_tracks(banner_pulls, {}, {})["rows"][0]
    assert (row["a"][0]["cat"], row["b"][0]["cat"]) == ("Bahamut", "Kasli")


def test_build_tracks_flags_a_rare_dupe_switch():
    # 1A and 2A are the same rare cat -> godfat rerolls 2A and jumps tracks.
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Jurassic Cat", R)]}
    assert build_tracks(banner_pulls, rerolls, {})["rows"][1]["a"][0]["switch"] is True


def test_build_tracks_cell_shows_the_rerolled_cat_not_the_dupe():
    # On a rare-dupe reroll the cell must show the cat you actually obtain (Jurassic Cat),
    # not the pre-reroll dupe (Pogo), so the target highlight lands on the right name.
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Jurassic Cat", R)]}
    cell = build_tracks(banner_pulls, rerolls, {})["rows"][1]["a"][0]
    assert cell["cat"] == "Jurassic Cat"
    assert cell["arrow"]["to"] == "3B"


def test_build_tracks_arrow_only_when_switched():
    # A normal (non-dupe) pull continues on its own track, so no jump arrow is shown.
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    assert build_tracks(banner_pulls, {}, {})["rows"][0]["a"][0]["arrow"] is None


def test_build_tracks_highlights_the_path_and_target():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    track = build_tracks(banner_pulls, {}, {}, path={"X": {0}}, targets={"X": {0}})
    entry = track["rows"][0]["a"][0]
    assert (entry["on_path"], entry["target"]) == (True, True)


def test_plan_highlight_keys_indices_by_representative_banner():
    option = SubsetPlan(frozenset({"Bahamut"}), Path((Pull(0, "Y", "Bahamut", U),), 1, 0))
    path, targets, _ = plan_highlight(option, {"X": ["X", "Y"], "Y": ["X", "Y"]})
    assert (path, targets) == ({"X": {0}}, {"X": {0}})


def test_build_tracks_shows_the_guaranteed_uber_not_the_normal_roll():
    # A guaranteed multi obtains an uber at a position whose normal roll is something else;
    # the on-path cell must show the uber the plan gets (Trixi), not the normal roll (Shaman).
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    pulled = {"X": {0: Pull(0, "X", "Trixi the Merc", U)}}
    cell = build_tracks(banner_pulls, {}, {}, path={"X": {0}}, targets={"X": {0}}, pulled=pulled)
    entry = cell["rows"][0]["a"][0]
    assert entry["cat"] == "Trixi the Merc"
    assert entry["rarity"] == "Uber Super Rare"
    assert entry["target"] is True


def test_build_tracks_flags_unowned_uber_as_new():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    entry = build_tracks(banner_pulls, {}, {}, owned=set())["rows"][0]["a"][0]
    assert entry["new"] is True


def test_build_tracks_owned_uber_is_not_new():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    entry = build_tracks(banner_pulls, {}, {}, owned={"Bahamut"})["rows"][0]["a"][0]
    assert entry["new"] is False


def test_build_tracks_rare_cat_is_never_new():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R)]}
    entry = build_tracks(banner_pulls, {}, {}, owned=set())["rows"][0]["a"][0]
    assert entry["new"] is False


def test_build_tracks_off_path_cell_keeps_the_normal_roll():
    # The same position off the plan's path still shows its normal roll.
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    pulled = {"X": {0: Pull(0, "X", "Trixi the Merc", U)}}
    cell = build_tracks(banner_pulls, {}, {}, path={}, targets={}, pulled=pulled)
    assert cell["rows"][0]["a"][0]["cat"] == "Shaman Cat"


def test_plan_summary_reports_cost_label_for_a_ticket_plan():
    leg = Leg("X", "Single pull", 0, (Pull(0, "X", "Bahamut", U),))
    option = SubsetPlan(frozenset({"Bahamut"}), Path(leg.pulls, 1, 0, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["cost_label"] == "1 ticket"


def test_plan_summary_lists_the_pulled_cats_per_leg():
    leg = Leg("X", "Single pull", 0, (Pull(0, "X", "Bahamut", U),))
    option = SubsetPlan(frozenset({"Bahamut"}), Path(leg.pulls, 1, 0, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["cats"] == ["Bahamut"]


def test_plan_summary_counts_ticket_funded_single_pulls():
    pulls = tuple(Pull(i, "X", "Bahamut", U) for i in range(3))
    leg = Leg("X", "Single pull", 0, pulls)
    option = SubsetPlan(frozenset({"Bahamut"}), Path(pulls, 3, 0, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["tickets"] == 3


def test_plan_summary_splits_a_mixed_single_pull_leg_into_tickets_and_catfood():
    pulls = tuple(Pull(i, "X", "Bahamut", U) for i in range(3))
    leg = Leg("X", "Single pull", 150, pulls)  # two ticket draws + one catfood draw
    option = SubsetPlan(frozenset({"Bahamut"}), Path(pulls, 2, 1, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["tickets"] == 2


def test_plan_summary_never_reads_a_catfood_multi_roll_as_tickets():
    pulls = tuple(Pull(i, "X", "Bahamut", U) for i in range(11))
    leg = Leg("X", "11-roll (guaranteed)", 1500, pulls)
    option = SubsetPlan(frozenset({"Bahamut"}), Path(pulls, 0, 10, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["tickets"] == 0
