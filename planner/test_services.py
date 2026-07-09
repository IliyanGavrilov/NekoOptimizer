import json
from datetime import date

import pytest

from neko.gachadata import GachaEventRow
from neko.graph import build_graphs
from neko.models import BannerRolls, Leg, Path, Pull, Rarity, TrackPull
from neko.search import Multi
from neko.subsets import SubsetPlan
from planner.models import Banner, Cat, Unit
from planner.services import (
    ADDONS_LABEL,
    REGULARS_LABEL,
    WIKI_BASE,
    TrackMarks,
    banner_titles,
    build_tracks,
    capped_banner_limits,
    collection_sections,
    cost_label,
    equivalent_banners,
    newly_added_ubers,
    picker_groups,
    plan_highlight,
    plan_seed,
    plan_shared,
    plan_summary,
    series_names,
    set_sections,
    subset_solutions,
    trace_marks,
    wiki_url,
)

U = Rarity.UBER_SUPER_RARE
R = Rarity.RARE


def test_capped_banner_limits_matches_only_platinum_and_legend():
    names = ["Platinum Capsules", "Legend Capsules", "Epicfest"]
    assert capped_banner_limits(names, 0) == {"Platinum Capsules": 0, "Legend Capsules": 0}


def test_capped_banner_limits_matches_the_real_capsule_run_names():
    names = [
        "Get an Uber Rare Cat!! 100% Uber drop Rate in the PLATINUM CAPSULES!",
        "Get a Guaranteed Uber or Legend Rare from the Legend Capsules!",
    ]
    assert capped_banner_limits(names, 0) == dict.fromkeys(names, 0)


def test_capped_banner_limits_ignores_banners_that_merely_mention_legend():
    # Collabs/fests name a "Limited Legend" or "Legend Rare drop rate" but roll on
    # catfood like any banner - they must not be treated as scarce-ticket capsules.
    names = [
        "EVANGELION Collab Capsules with a Limited Legend and Mass Production EVA!",
        "Increased Uber and Legend Rare drop rate! 90M DL Special Capsules!",
        "Double the Uber / Legend chances! ★ Glorious gods of the Cat pantheon!",
    ]
    assert capped_banner_limits(names, 0) == {}


def test_collection_sections_orders_rarities_cheapest_to_rarest():
    units = [Unit(rarity=r) for r in ("Uber Super Rare", "Special", "Normal")]
    assert [r for r, _ in collection_sections(units)] == ["Normal", "Special", "Uber Super Rare"]


def test_collection_sections_puts_blank_rarity_under_unknown_last():
    units = [Unit(rarity=""), Unit(rarity="Legend Rare")]
    assert [r for r, _ in collection_sections(units)] == ["Legend Rare", "Unknown"]


def _dated_banner(name, start, end):
    banner = Banner.objects.create(name=name, start=start, end=end)
    cat = Cat.objects.create(name=f"{name} cat")
    cat.banners.add(banner)
    return cat


def _uber(unit_id, set_name=""):
    return Unit(unit_id=unit_id, name=f"U{unit_id}", rarity="Uber Super Rare", set_name=set_name)


def test_set_sections_orders_named_sets_by_dictionary_position():
    zeus = _uber(257, set_name="The Almighties")
    luga = _uber(34, set_name="Tales of the Nekoluga")
    sections = set_sections([zeus, luga], events=[], pools={}, series={})
    assert [label for label, _ in sections] == ["Tales of the Nekoluga", "The Almighties"]


def test_set_sections_subdivides_a_set_by_rarity():
    ice = _uber(42, set_name="The Dynamites")
    pogo = Unit(unit_id=43, name="Pogo", rarity="Rare", set_name="The Dynamites")
    (section,) = set_sections([ice, pogo], events=[], pools={}, series={})
    assert section == ("The Dynamites", [("Rare", [pogo]), ("Uber Super Rare", [ice])])


def test_set_sections_homes_a_collab_unit_to_its_smallest_pool():
    sonic = _uber(700)
    events = [
        _run(date(2026, 1, 1), date(2026, 1, 5), 1, "Sonic collab!"),
        _run(date(2026, 2, 1), date(2026, 2, 5), 2, "Umbrella capsules"),
    ]
    pools = {1: [700, 701], 2: list(range(690, 790))}
    sections = set_sections([sonic], events, pools, {1: 10, 2: 11})
    assert [label for label, _ in sections] == ["Sonic collab!"]


def test_set_sections_lists_a_rerun_series_once_under_its_latest_text():
    miku = _uber(650)
    events = [
        _run(date(2025, 1, 1), date(2025, 1, 5), 1, "Miku is back!"),
        _run(date(2026, 1, 1), date(2026, 1, 5), 2, "Miku returns again!"),
    ]
    sections = set_sections([miku], events, {1: [650], 2: [650]}, {1: 7, 2: 7})
    assert [label for label, _ in sections] == ["Miku returns again!"]


def test_set_sections_puts_shared_pool_cats_under_regulars():
    rover = Unit(unit_id=50, name="Rover Cat", rarity="Rare")
    events = [_run(date(2026, 1, 1), date(2026, 1, 5), i, f"Set {i}") for i in range(1, 6)]
    sections = set_sections(
        [rover], events, {i: [50] for i in range(1, 6)}, {i: i for i in range(1, 6)}
    )
    assert [label for label, _ in sections] == [REGULARS_LABEL]


def test_set_sections_leaves_non_gacha_units_out():
    moneko = Unit(unit_id=900, name="Moneko", rarity="Special")
    assert set_sections([moneko], events=[], pools={}, series={}) == []


def test_set_sections_homes_an_unnamed_legend_with_its_set():
    dyna = [_uber(42, "The Dynamites"), _uber(43, "The Dynamites")]
    vaji = [_uber(71, "Vajiras"), _uber(72, "Vajiras")]
    legend = Unit(unit_id=600, name="Dyna Legend", rarity="Legend Rare")
    events = [
        _run(date(2026, 1, 1), date(2026, 1, 5), 1, "Dynamites are back!"),
        _run(date(2026, 2, 1), date(2026, 2, 5), 2, "UBERFEST!"),
    ]
    pools = {1: [42, 43, 600], 2: [42, 43, 71, 72, 600]}
    sections = set_sections([*dyna, *vaji, legend], events, pools, {1: 1, 2: 19})
    assert ("Legend Rare", [legend]) in dict(sections)["The Dynamites"]


def test_set_sections_leads_with_the_regulars():
    rover = Unit(unit_id=50, name="Rover Cat", rarity="Rare")
    ice = _uber(42, "The Dynamites")
    events = [_run(date(2026, 1, 1), date(2026, 1, 5), i, f"Set {i}") for i in range(1, 6)]
    pools = {i: [50, 42] for i in range(1, 6)}
    sections = set_sections([rover, ice], events, pools, {i: i for i in range(1, 6)})
    assert [label for label, _ in sections] == [REGULARS_LABEL, "The Dynamites"]


def test_set_sections_splits_shared_cats_missing_from_most_banners_into_addons():
    rover = Unit(unit_id=50, name="Rover Cat", rarity="Rare")
    neneko = Unit(unit_id=60, name="Neneko", rarity="Super Rare")
    events = [_run(date(2026, 1, 1), date(2026, 1, 5), i, f"Set {i}") for i in range(1, 11)]
    pools = {i: [50, 60] if i <= 4 else [50] for i in range(1, 11)}
    sections = set_sections([rover, neneko], events, pools, {i: i for i in range(1, 11)})
    assert [label for label, _ in sections] == [REGULARS_LABEL, ADDONS_LABEL]
    assert dict(sections)[ADDONS_LABEL] == [("Super Rare", [neneko])]


def _fest_fixture():
    dyna = [_uber(100, "The Dynamites"), _uber(101, "The Dynamites")]
    uf = [_uber(200, "UBER FEST"), _uber(201, "UBER FEST")]
    ef = [_uber(300, "EPICFEST"), _uber(301, "EPICFEST")]
    izanagi = Unit(unit_id=600, name="Izanagi", rarity="Legend Rare")
    events = [
        _run(date(2026, 1, 1), date(2026, 1, 5), 1, "Dynamites!"),
        _run(date(2026, 2, 1), date(2026, 2, 5), 2, "Uberfest!"),
        _run(date(2026, 3, 1), date(2026, 3, 5), 3, "Epicfest!"),
        _run(date(2026, 4, 1), date(2026, 4, 5), 4, "Superfest!"),
    ]
    pools = {
        1: [100, 101],
        2: [100, 101, 200, 201, 600],
        3: [100, 101, 300, 301],
        4: [100, 101, 200, 201, 300, 301, 600],
    }
    series = {1: 1, 2: 19, 3: 27, 4: 42}
    return [*dyna, *uf, *ef, izanagi], events, pools, series


def test_set_sections_lists_a_fest_exclusive_on_every_fest_that_carries_it():
    units, events, pools, series = _fest_fixture()
    sections = dict(set_sections(units, events, pools, series))
    assert REGULARS_LABEL not in sections
    izanagi = units[-1]
    assert ("Legend Rare", [izanagi]) in sections["UBERFEST"]
    assert ("Legend Rare", [izanagi]) in sections["SUPERFEST"]
    assert ("Legend Rare", [izanagi]) not in sections["EPICFEST"]


def test_set_sections_bundles_covered_sets_but_not_the_general_uber_pool():
    units, events, pools, series = _fest_fixture()
    sections = dict(set_sections(units, events, pools, series))
    superfest = [u.name for _, bin in sections["SUPERFEST"] for u in bin]
    assert superfest == ["U200", "U201", "U300", "U301", "Izanagi"]
    assert [u.name for _, bin in sections["The Dynamites"] for u in bin] == ["U100", "U101"]


def test_set_sections_lists_the_standard_legends_on_legend_rate_fests():
    dyna = [_uber(100, "The Dynamites"), _uber(101, "The Dynamites")]
    vaji = [_uber(110, "Vajiras"), _uber(111, "Vajiras")]
    legends = [
        Unit(unit_id=700, name="Musashi", rarity="Legend Rare"),
        Unit(unit_id=701, name="Jeanne", rarity="Legend Rare"),
    ]
    events = [
        _run(date(2026, 1, 1), date(2026, 1, 5), 1, "Dynamites!"),
        _run(date(2026, 2, 1), date(2026, 2, 5), 2, "Vajiras!"),
        _run(date(2026, 3, 1), date(2026, 3, 5), 3, "Royal Fest!"),
    ]
    pools = {1: [100, 101, 700], 2: [110, 111, 701], 3: [100, 110, 700, 701]}
    sections = dict(set_sections([*dyna, *vaji, *legends], events, pools, {1: 1, 2: 2, 3: 50}))
    assert ("Legend Rare", legends) in sections["RoyalFest"]
    assert ("Legend Rare", [legends[0]]) in sections["The Dynamites"]


def test_series_names_pick_each_sets_smallest_carrier():
    dyna = [_uber(42, "The Dynamites"), _uber(43, "The Dynamites")]
    events = [
        _run(date(2026, 1, 1), date(2026, 1, 5), 1, "Dynamites!"),
        _run(date(2026, 2, 1), date(2026, 2, 5), 2, "UBERFEST!"),
    ]
    pools = {1: [42, 43], 2: [42, 43, 71, 72]}
    names = series_names(dyna, events, pools, {1: 1, 2: 19}, tickets={})
    assert names == {1: "The Dynamites", 19: "UBERFEST"}


def test_series_names_label_the_fests():
    events = [_run(date(2026, 1, 1), date(2026, 1, 5), 7, "Lone Moon Lunos added!")]
    assert series_names([], events, {7: [500]}, {7: 42}, tickets={}) == {42: "SUPERFEST"}


def test_series_names_label_ticket_gachas():
    events = [_run(date(2026, 1, 1), date(2026, 1, 5), 953, "Get an Uber Rare Cat!!")]
    names = series_names([], events, {953: [500]}, {953: 21}, tickets={953: 29})
    assert names == {21: "Platinum Capsules"}


@pytest.mark.django_db
def test_banner_titles_map_pools_to_series_names():
    Unit.objects.create(
        unit_id=42, name="Ice Cat", rarity="Uber Super Rare", set_name="The Dynamites"
    )
    events = [_run(date(2026, 1, 1), date(2026, 1, 5), 7, "Dynamites!")]
    titles = banner_titles(events=events, pools={7: [42]}, series={7: 1}, tickets={})
    assert titles == {7: "The Dynamites"}


@pytest.mark.django_db
def test_picker_groups_titles_rows_from_their_pool():
    today = date(2026, 7, 3)
    events = [_run(date(2026, 6, 26), date(2026, 7, 10), 5, "Brave new adventurers join!")]
    groups = dict(picker_groups([], today=today, events=events, titles={5: "The Dynamites"}))
    assert [(n, t) for n, t, _d, _c in groups["Available now"]] == [
        ("Brave new adventurers join!", "The Dynamites")
    ]


def _run(start, end, pool_id, name):
    return GachaEventRow(
        f"{start}_{pool_id}", name, start, end, pool_id, 7000, 2500, 500, 0, False, False
    )


@pytest.mark.django_db
def test_picker_groups_lists_each_scheduled_run_separately():
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
    now = [(name, dates) for name, _title, dates, _ in groups["Available now"]]
    assert now == [
        ("Platinum", (date(2026, 4, 24), date(2026, 7, 10))),
        ("Trixi", (date(2026, 6, 26), date(2026, 7, 3))),
    ]
    upcoming = [(n, d) for n, _t, d, _ in groups["Upcoming"]]
    assert upcoming == [("Platinum", (date(2026, 7, 11), sentinel))]
    assert groups["Available now"][0][3] == [("Uber Super Rare", [cat])]
    assert groups["Upcoming"][0][3] == [("Uber Super Rare", [cat])]


@pytest.mark.django_db
def test_picker_groups_keeps_unscheduled_past_banners_db_dated():
    today = date(2026, 7, 3)
    _dated_banner("OldFest", date(2026, 5, 1), date(2026, 5, 4))
    groups = dict(picker_groups(Cat.objects.all(), today=today, events=[]))
    assert [(n, d) for n, _t, d, _ in groups["Past"]] == [
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
    assert [(n, d) for n, _t, d, _ in groups["Past"]] == [
        ("Fest", (date(2026, 5, 1), date(2026, 5, 5))),
        ("Fest", (date(2026, 2, 1), date(2026, 2, 5))),
    ]
    newest, oldest = groups["Past"]
    assert newest[3] == [("Uber Super Rare", [cat])]
    assert oldest[3] == []


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


def _gacha_event(name, start, pool_id):
    return GachaEventRow(name, name, start, start, pool_id, 7, 2, 1, 0, False, False)


def test_newly_added_ubers_are_the_ubers_debuting_with_a_banner_run():
    # "Late Uber" premieres on the March festival; the June banner picks it up too,
    # but only its own first-ever uber counts as new there.
    events = [
        _gacha_event("base", date(2025, 1, 1), 10),
        _gacha_event("fest", date(2025, 3, 1), 20),
        _gacha_event("rerun", date(2025, 6, 1), 11),
    ]
    pools = {10: [1], 20: [2], 11: [1, 2, 3]}
    units = {1: ("Base Uber", U.value), 2: ("Late Uber", U.value), 3: ("June Uber", U.value)}
    added = newly_added_ubers(events=events, pools=pools, units=units)
    assert added == {"base": {"Base Uber"}, "fest": {"Late Uber"}, "rerun": {"June Uber"}}


def test_newly_added_ubers_keys_a_rerun_name_by_its_latest_run():
    # The banner reruns under the same name with the same pool: its January debuts
    # must not resurface as "new" on the June run.
    events = [
        _gacha_event("fest", date(2025, 1, 1), 10),
        _gacha_event("fest", date(2025, 6, 1), 10),
    ]
    units = {1: ("Old Uber", U.value)}
    assert newly_added_ubers(events=events, pools={10: [1]}, units=units) == {}


def test_build_tracks_flags_an_uber_new_to_its_banner():
    pulls = [TrackPull(1, "A", "Added Uber", U)]
    debuts = {"X": {"Added Uber"}}
    cell = build_tracks({"X": pulls}, {}, {}, debuts=debuts)["rows"][0]["a"][0]
    assert cell["debut"] is True
    # Not flagged on a banner the uber isn't new to.
    assert build_tracks({"Y": pulls}, {}, {}, debuts=debuts)["rows"][0]["a"][0]["debut"] is False


def test_build_tracks_tags_a_cell_with_its_catalogue_unit_id():
    pulls = [TrackPull(1, "A", "Bahamut", U)]
    cell = build_tracks({"X": pulls}, {}, {}, unit_ids={"Bahamut": 25})["rows"][0]["a"][0]
    assert cell["uid"] == 25
    # A name with no catalogued unit (or no map at all) just falls back to text.
    assert build_tracks({"X": pulls}, {}, {})["rows"][0]["a"][0]["uid"] is None


def test_build_tracks_renders_up_to_the_requested_row_count():
    pulls = [TrackPull(pos, track, "Bahamut", U) for pos in range(1, 151) for track in ("A", "B")]
    assert len(build_tracks({"X": pulls}, {}, {})["rows"]) == 100  # default cap
    assert len(build_tracks({"X": pulls}, {}, {}, rows=140)["rows"]) == 140


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
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Jurassic Cat", R)]}
    assert build_tracks(banner_pulls, rerolls, {})["rows"][1]["a"][0]["switch"] is True


def test_build_tracks_dupe_cell_reads_nominal_first():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Jurassic Cat", R)]}
    cell = build_tracks(banner_pulls, rerolls, {})["rows"][1]["a"][0]
    assert (cell["cat"], cell["switch"]) == ("Pogo", True)
    assert (cell["alt"]["cat"], cell["alt"]["to"]) == ("Jurassic Cat", "3B")


def test_build_tracks_no_branch_on_a_normal_pull():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    assert build_tracks(banner_pulls, {}, {})["rows"][0]["a"][0]["alt"] is None


def test_build_tracks_exposes_each_cells_seeds_for_the_details_view():
    banner_pulls = {
        "X": [
            TrackPull(1, "A", "Bahamut", U, seed=222, rarity_seed=111),
            TrackPull(1, "B", "Kasli", U, seed=444, rarity_seed=333),
        ]
    }
    row = build_tracks(banner_pulls, {}, {})["rows"][0]
    assert row["a_details"] == {"rarity_seed": 111, "slot_seed": 222}
    assert row["b_details"] == {"rarity_seed": 333, "slot_seed": 444}


def test_build_tracks_a_track_dupe_branch_points_right_towards_b():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Jurassic Cat", R)]}
    assert build_tracks(banner_pulls, rerolls, {})["rows"][1]["a"][0]["alt"]["left"] is False


def test_build_tracks_b_track_dupe_branch_points_left_towards_a():
    banner_pulls = {"X": [TrackPull(1, "B", "Pogo", R), TrackPull(2, "B", "Pogo", R)]}
    rerolls = {"X": [TrackPull(2, "B", "Jurassic Cat", R)]}
    assert build_tracks(banner_pulls, rerolls, {})["rows"][1]["b"][0]["alt"]["left"] is True


def test_build_tracks_shows_a_conditional_reroll_on_a_realized_bounce_cell():
    banner_pulls = {"X": [TrackPull(1, "A", "Aset", U), TrackPull(2, "A", "Onmyoji", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Pirate", R, seed=9, steps=1, realized=True)]}
    cell = build_tracks(banner_pulls, rerolls, {})["rows"][1]["a"][0]
    assert (cell["cat"], cell["switch"]) == ("Onmyoji", False)
    assert cell["alt"] == {"cat": "Pirate", "to": "3B", "left": False, "seed": 9, "target": False}


def test_build_tracks_keeps_unrealized_conditional_rerolls_quiet():
    banner_pulls = {"X": [TrackPull(1, "A", "Aset", U), TrackPull(2, "A", "Onmyoji", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Pirate", R, steps=1)]}
    assert build_tracks(banner_pulls, rerolls, {})["rows"][1]["a"][0]["alt"] is None


def test_build_tracks_switch_cell_keeps_both_branch_seeds():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R, seed=5)]}
    rerolls = {"X": [TrackPull(2, "A", "Jurassic Cat", R, seed=9, steps=1)]}
    row = build_tracks(banner_pulls, rerolls, {})["rows"][1]
    cell = row["a"][0]
    assert (cell["cat"], cell["switch"]) == ("Pogo", True)
    assert cell["alt"] == {
        "cat": "Jurassic Cat",
        "to": "3B",
        "left": False,
        "seed": 9,
        "target": False,
    }
    assert (row["a_seed"], row["a_cat"]) == (5, "Pogo")


def test_build_tracks_guaranteed_entry_carries_its_after_seed():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "Kasli", U, seed=42)]}
    track = build_tracks(banner_pulls, {}, {}, guaranteed=guaranteed)
    assert track["rows"][0]["ga"][0]["seed"] == 42


def test_build_tracks_highlights_the_path_and_target():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    marks = TrackMarks(path={"X": {0}}, targets={"X": {0: "Bahamut"}})
    track = build_tracks(banner_pulls, {}, {}, marks=marks)
    entry = track["rows"][0]["a"][0]
    assert (entry["on_path"], entry["target"]) == (True, True)


def test_build_tracks_target_pill_follows_the_dupe_branch():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R)]}
    rerolls = {"X": [TrackPull(2, "A", "Jurassic Cat", R)]}
    marks = TrackMarks(path={"X": {2}}, targets={"X": {2: "Jurassic Cat"}})
    track = build_tracks(banner_pulls, rerolls, {}, marks=marks)
    cell = track["rows"][1]["a"][0]
    assert (cell["target"], cell["alt"]["target"]) == (False, True)


def test_plan_highlight_keys_indices_by_representative_banner():
    option = SubsetPlan(frozenset({"Bahamut"}), Path((Pull(0, "Y", "Bahamut", U),), 1, 0))
    marks = plan_highlight(option, {"X": ["X", "Y"], "Y": ["X", "Y"]})
    assert (marks.path, marks.targets) == ({"X": {0}}, {"X": {0: "Bahamut"}})
    assert (marks.gpath, marks.gtargets) == ({}, {})


def test_plan_highlight_routes_guaranteed_pulls_to_the_guaranteed_column():
    pulls = (Pull(0, "X", "Cat", R), Pull(0, "X", "Mecha", U, guaranteed=True))
    option = SubsetPlan(frozenset({"Mecha"}), Path(pulls, 0, 3))
    marks = plan_highlight(option, {})
    assert (marks.path, marks.targets) == ({"X": {0}}, {})
    assert (marks.gpath, marks.gtargets) == ({"X": {0}}, {"X": {0: "Mecha"}})


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


def test_build_tracks_marks_a_future_uber_placeholder_green_and_new():
    banner_pulls = {"X": [TrackPull(1, "A", "Future Uber 1", U)]}
    entry = build_tracks(banner_pulls, {}, {}, owned=set())["rows"][0]["a"][0]
    # A placeholder is by definition uncollected (green name) and new to the banner
    # (the "new" pill); ``future`` renders it as plain text instead of a popup link.
    assert entry["future"] is True
    assert entry["new"] is True and entry["debut"] is True
    assert entry["owned"] is False and entry["wanted"] is False


def test_build_tracks_real_cats_are_not_future():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    entry = build_tracks(banner_pulls, {}, {}, owned=set())["rows"][0]["a"][0]
    assert entry["future"] is False


def test_build_tracks_future_map_fills_the_legend_steppers():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R)]}
    track = build_tracks(banner_pulls, {}, {}, future={"X": 2})
    assert track["show_future"] is True and track["padded"] is True
    assert track["legend"][0]["future"] == 2
    assert json.loads(track["legend"][0]["keys"]) == ["X"]


def test_build_tracks_without_a_future_map_renders_no_steppers():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R)]}
    track = build_tracks(banner_pulls, {}, {})
    assert track["show_future"] is False and track["padded"] is False
    assert "keys" not in track["legend"][0]


def test_trace_marks_light_the_walk_up_to_the_clicked_cell():
    banner_pulls = {
        "X": [
            TrackPull(1, "A", "Pogo", R),
            TrackPull(2, "A", "Kasa Jizo", U),
            TrackPull(3, "A", "Bahamut", U),
        ]
    }
    marks = trace_marks(banner_pulls, {}, {}, "1", 4)
    assert marks.path == {"X": {0, 2, 4}}
    assert marks.targets == {"X": {4: "Bahamut"}}


def test_trace_marks_follow_a_dupe_hop():
    banner_pulls = {
        "X": [
            TrackPull(1, "A", "Pogo", R),
            TrackPull(2, "A", "Pogo", R),
            TrackPull(3, "B", "Kasa Jizo", U),
        ]
    }
    rerolls = {"X": [TrackPull(2, "A", "Sniper Cat", R, steps=1, realized=True)]}
    marks = trace_marks(banner_pulls, rerolls, {}, "1", 5)
    assert marks.path == {"X": {0, 2, 5}}
    assert marks.targets == {"X": {5: "Kasa Jizo"}}


def test_trace_marks_stop_when_a_hop_jumps_past_the_cell():
    banner_pulls = {
        "X": [
            TrackPull(1, "A", "Pogo", R),
            TrackPull(2, "A", "Pogo", R),
            TrackPull(3, "A", "Bahamut", U),
        ]
    }
    rerolls = {"X": [TrackPull(2, "A", "Sniper Cat", R, steps=1, realized=True)]}
    marks = trace_marks(banner_pulls, rerolls, {}, "1", 4)
    # The reroll at 2A hops to 3B, so 3A is unreachable by straight singles on this seed:
    # nothing before it lights up - just the clicked cat gets its pill (godfat's pick).
    assert marks.path == {}
    assert marks.targets == {"X": {4: "Bahamut"}}
    assert marks.shared == {}


def test_trace_marks_guaranteed_click_marks_the_column_uber():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Kasa Jizo", U)]}
    guaranteed = {"X": [TrackPull(1, "A", "Bahamut", U), TrackPull(2, "A", "Kasli", U)]}
    marks = trace_marks(banner_pulls, {}, {}, "1", 2, guaranteed_pulls=guaranteed, guaranteed=True)
    # The singles that reach 2A light, and the guaranteed column's uber there is the pill.
    assert marks.path == {"X": {0, 2}}
    assert marks.gpath == {"X": {2}}
    assert marks.gtargets == {"X": {2: "Kasli"}}
    assert marks.targets == {}


def test_trace_marks_guaranteed_click_on_unreachable_cell_marks_only_the_uber():
    banner_pulls = {
        "X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R), TrackPull(3, "A", "X", U)]
    }
    guaranteed = {
        "X": [
            TrackPull(1, "A", "G1", U),
            TrackPull(2, "A", "G2", U),
            TrackPull(3, "A", "G3", U),
        ]
    }
    rerolls = {"X": [TrackPull(2, "A", "Sniper Cat", R, steps=1, realized=True)]}
    marks = trace_marks(
        banner_pulls, rerolls, {}, "1", 4, guaranteed_pulls=guaranteed, guaranteed=True
    )
    # 3A's start is unreachable, so the guaranteed uber stands alone - no lit path.
    assert marks.path == {}
    assert marks.gpath == {}
    assert marks.gtargets == {"X": {4: "G3"}}


def test_trace_marks_guaranteed_click_without_a_guarantee_marks_nothing():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Kasa Jizo", U)]}
    marks = trace_marks(banner_pulls, {}, {}, "1", 2, guaranteed_pulls={}, guaranteed=True)
    assert marks == TrackMarks()


def test_trace_marks_share_steps_with_walk_alike_banners():
    banner_pulls = {
        "X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Kasa Jizo", U)],
        "Y": [TrackPull(1, "A", "Bath Cat", R), TrackPull(2, "A", "Kasa Jizo", U)],
    }
    marks = trace_marks(banner_pulls, {}, {}, "1", 2)
    # Y walks the same path (a filler rare may differ) and gives the same target cat.
    assert marks.shared == {"Y": {0, 2}}


def test_trace_marks_ignore_a_stale_click():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R)]}
    assert trace_marks(banner_pulls, {}, {}, "9", 0).path == {}
    assert trace_marks(banner_pulls, {}, {}, "1", 400).path == {}


def test_build_tracks_marks_an_owned_cat():
    banner_pulls = {"X": [TrackPull(1, "A", "Pogo", R)]}
    entry = build_tracks(banner_pulls, {}, {}, owned={"Pogo"})["rows"][0]["a"][0]
    assert entry["owned"] is True


def test_build_tracks_stars_a_wishlisted_cat():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U)]}
    entry = build_tracks(banner_pulls, {}, {}, wanted={"Bahamut"})["rows"][0]["a"][0]
    assert entry["wanted"] is True


def test_build_tracks_guaranteed_uber_can_be_wishlisted():
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "Trixi the Merc", U)]}
    row = build_tracks(banner_pulls, {}, {}, guaranteed=guaranteed, wanted={"Trixi the Merc"})[
        "rows"
    ][0]
    assert row["ga"][0]["wanted"] is True


def test_build_tracks_highlights_the_guaranteed_column_cell():
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "Trixi the Merc", U)]}
    marks = TrackMarks(path={"X": {0}}, gpath={"X": {0}}, gtargets={"X": {0: "Trixi the Merc"}})
    track = build_tracks(banner_pulls, {}, {}, marks=marks, guaranteed=guaranteed)
    entry = track["rows"][0]["ga"][0]
    assert (entry["on_path"], entry["target"]) == (True, True)
    assert track["rows"][0]["a"][0]["cat"] == "Shaman Cat"


def test_build_tracks_guaranteed_cell_off_path_is_not_highlighted():
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "Trixi the Merc", U)]}
    entry = build_tracks(banner_pulls, {}, {}, guaranteed=guaranteed)["rows"][0]["ga"][0]
    assert (entry["on_path"], entry["target"]) == (False, False)


def test_build_tracks_renders_the_guaranteed_columns():
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R), TrackPull(1, "B", "Pogo", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "Trixi the Merc", U), TrackPull(1, "B", "Kasli", U)]}
    track = build_tracks(banner_pulls, {}, {}, guaranteed=guaranteed)
    assert track["has_guaranteed"] is True
    row = track["rows"][0]
    assert [e["cat"] for e in row["ga"]] == ["Trixi the Merc"]
    assert [e["cat"] for e in row["gb"]] == ["Kasli"]
    assert row["ga"][0]["rarity"] == "Uber Super Rare"


def test_build_tracks_without_a_guarantee_omits_the_columns():
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    track = build_tracks(banner_pulls, {}, {}, guaranteed={"X": []})
    assert track["has_guaranteed"] is False
    assert track["rows"][0]["ga"] == []


def test_build_tracks_guaranteed_cell_stacks_only_guaranteed_banners():
    banner_pulls = {
        "X": [TrackPull(1, "A", "Shaman Cat", R)],
        "Y": [TrackPull(1, "A", "Pogo", R)],
    }
    guaranteed = {"X": [TrackPull(1, "A", "Trixi the Merc", U)], "Y": []}
    row = build_tracks(banner_pulls, {}, {}, guaranteed=guaranteed)["rows"][0]
    assert [(e["tag"], e["cat"]) for e in row["ga"]] == [("1", "Trixi the Merc")]


def test_build_tracks_guaranteed_uber_can_be_new():
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "Trixi the Merc", U)]}
    row = build_tracks(banner_pulls, {}, {}, owned=set(), guaranteed=guaranteed)["rows"][0]
    assert row["ga"][0]["new"] is True


def test_build_tracks_skips_an_empty_guaranteed_cell():
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "", U)]}
    track = build_tracks(banner_pulls, {}, {}, guaranteed=guaranteed)
    assert track["rows"][0]["ga"] == []


def test_build_tracks_row_carries_the_cell_dice_seed_and_cat():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U, seed=111)]}
    row = build_tracks(banner_pulls, {}, {})["rows"][0]
    assert (row["a_seed"], row["a_cat"]) == (111, "Bahamut")


def test_build_tracks_cell_dice_reads_any_banner_rolled_there():
    banner_pulls = {
        "X": [TrackPull(1, "A", "Pogo", R, seed=5)],
        "Y": [
            TrackPull(1, "A", "Kasli", U, seed=5),
            TrackPull(2, "A", "Pogo", R, seed=7),
        ],
    }
    track = build_tracks(banner_pulls, {}, {})
    assert (track["rows"][0]["a_seed"], track["rows"][1]["a_seed"]) == (5, 7)
    assert (track["rows"][0]["a_cat"], track["rows"][1]["a_cat"]) == ("", "Pogo")


def test_plan_seed_is_the_state_after_the_last_pull():
    graphs = build_graphs(
        {"X": [TrackPull(1, "A", "Cat", R, seed=7), TrackPull(2, "A", "Dog", R, seed=8)]}
    )
    plan = Path((Pull(0, "X", "Cat", R), Pull(2, "X", "Dog", R)), 2, 0)
    assert plan_seed(plan, graphs) == 8


def test_plan_seed_on_a_dupe_is_the_reroll_seed():
    graphs = build_graphs(
        {"X": [TrackPull(1, "A", "Cat", R, seed=7), TrackPull(2, "A", "Cat", R, seed=8)]},
        rerolls={"X": [TrackPull(2, "A", "Dog", R, seed=9)]},
    )
    plan = Path((Pull(2, "X", "Dog", R),), 1, 0)
    assert plan_seed(plan, graphs) == 9


def test_plan_seed_guaranteed_pull_reads_the_guaranteed_column():
    graphs = build_graphs(
        {"X": [TrackPull(1, "A", "Cat", R, seed=7)]},
        {"X": [TrackPull(1, "A", "Mecha", U, seed=10)]},
    )
    plan = Path((Pull(0, "X", "Mecha", U, guaranteed=True),), 0, 3)
    assert plan_seed(plan, graphs) == 10


def test_plan_seed_empty_plan_is_none():
    assert plan_seed(Path((), 0, 0), []) is None


def test_plan_seed_resolves_a_conditional_dupe_by_the_walk():
    graphs = build_graphs(
        {
            "X": [
                TrackPull(1, "A", "Dog", R, seed=1),
                TrackPull(2, "A", "Cat", R, seed=2),
                TrackPull(3, "A", "Cat", R, seed=3),
                TrackPull(4, "B", "Bird", R, seed=4),
            ]
        },
        rerolls={
            "X": [
                TrackPull(3, "A", "Bird", R, seed=5, steps=1),
                TrackPull(4, "B", "Fish", R, seed=6, steps=1),
            ]
        },
    )
    pulls = (
        Pull(0, "X", "Dog", R),
        Pull(2, "X", "Cat", R),
        Pull(4, "X", "Bird", R),
        Pull(7, "X", "Fish", R),
    )
    assert plan_seed(Path(pulls, 4, 0), graphs) == 6


def test_plan_summary_reports_cost_label_for_a_ticket_plan():
    leg = Leg("X", "Single pull", 0, (Pull(0, "X", "Bahamut", U),))
    option = SubsetPlan(frozenset({"Bahamut"}), Path(leg.pulls, 1, 0, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["cost_label"] == "1 ticket"


def test_plan_summary_lists_the_pulled_cats_per_leg():
    leg = Leg("X", "Single pull", 0, (Pull(0, "X", "Bahamut", U),))
    option = SubsetPlan(frozenset({"Bahamut"}), Path(leg.pulls, 1, 0, (leg,)))
    cats = plan_summary([option], {"X": ["X"]})[0]["legs"][0]["cats"]
    assert [c["name"] for c in cats] == ["Bahamut"]


def test_plan_summary_marks_the_targets_in_a_leg():
    leg = Leg("X", "Single pull", 0, (Pull(0, "X", "Bahamut", U), Pull(1, "X", "Pogo", R)))
    option = SubsetPlan(frozenset({"Bahamut"}), Path(leg.pulls, 2, 0, (leg,)))
    cats = plan_summary([option], {"X": ["X"]})[0]["legs"][0]["cats"]
    assert [c["target"] for c in cats] == [True, False]


def test_plan_summary_marks_owned_and_wishlisted_cats():
    leg = Leg("X", "Single pull", 0, (Pull(0, "X", "Pogo", R), Pull(1, "X", "Kasli", U)))
    option = SubsetPlan(frozenset({"Kasli"}), Path(leg.pulls, 2, 0, (leg,)))
    summary = plan_summary([option], {"X": ["X"]}, owned={"Pogo"}, wanted={"Kasli"})
    cats = summary[0]["legs"][0]["cats"]
    assert [(c["owned"], c["wanted"]) for c in cats] == [(True, False), (False, True)]


def test_plan_summary_flags_an_unowned_uber_as_new():
    leg = Leg("X", "Single pull", 0, (Pull(0, "X", "Kasli", U),))
    option = SubsetPlan(frozenset({"Kasli"}), Path(leg.pulls, 1, 0, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["cats"][0]["new"] is True


def test_plan_summary_counts_ticket_funded_single_pulls():
    pulls = tuple(Pull(i, "X", "Bahamut", U) for i in range(3))
    leg = Leg("X", "Single pull", 0, pulls)
    option = SubsetPlan(frozenset({"Bahamut"}), Path(pulls, 3, 0, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["tickets"] == 3


def test_plan_summary_splits_a_mixed_single_pull_leg_into_tickets_and_catfood():
    pulls = tuple(Pull(i, "X", "Bahamut", U) for i in range(3))
    leg = Leg("X", "Single pull", 150, pulls)
    option = SubsetPlan(frozenset({"Bahamut"}), Path(pulls, 2, 1, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["tickets"] == 2


def test_plan_summary_never_reads_a_catfood_multi_roll_as_tickets():
    pulls = tuple(Pull(i, "X", "Bahamut", U) for i in range(11))
    leg = Leg("X", "11-roll (guaranteed)", 1500, pulls)
    option = SubsetPlan(frozenset({"Bahamut"}), Path(pulls, 0, 10, (leg,)))
    assert plan_summary([option], {"X": ["X"]})[0]["legs"][0]["tickets"] == 0


def _single(index, banner, cat, rarity, cost=0):
    return Leg(banner, "Single pull", cost, (Pull(index, banner, cat, rarity),))


def _plan(targets, moves, tickets=0, catfood=0):
    pulls = tuple(pull for leg in moves for pull in leg.pulls)
    return SubsetPlan(frozenset(targets), Path(pulls, tickets, catfood, tuple(moves)))


def test_plan_shared_marks_a_filler_pull_even_when_the_cat_differs():
    graphs = build_graphs(
        {
            "X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Bahamut", U)],
            "Y": [TrackPull(1, "A", "Rover Cat", R), TrackPull(2, "A", "Kasli", U)],
        }
    )
    option = _plan({"Bahamut"}, (_single(0, "X", "Pogo", R), _single(2, "X", "Bahamut", U)), 2)
    shared, gshared = plan_shared(option, graphs, {})
    assert shared == {"Y": {0}}
    assert gshared == {}


def test_plan_shared_marks_a_target_pull_where_the_same_cat_drops():
    graphs = build_graphs(
        {"X": [TrackPull(1, "A", "Bahamut", U)], "Y": [TrackPull(1, "A", "Bahamut", U)]}
    )
    option = _plan({"Bahamut"}, (_single(0, "X", "Bahamut", U),), 1)
    shared, _gshared = plan_shared(option, graphs, {})
    assert shared == {"Y": {0}}


def test_plan_shared_rejects_a_pull_whose_walk_diverges():
    graphs = build_graphs(
        {
            "X": [TrackPull(1, "A", "Bahamut", U), TrackPull(2, "A", "Jurassic Cat", R)],
            "Y": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Pogo", R)],
        },
        rerolls={"Y": [TrackPull(2, "A", "Jurassic Cat", R)]},
    )
    option = _plan({"Jurassic Cat"}, (_single(2, "X", "Jurassic Cat", R),), 1)
    shared, _gshared = plan_shared(option, graphs, {})
    assert shared == {}


def test_plan_shared_rejects_a_filler_swap_that_would_dupe_the_next_pull():
    graphs = build_graphs(
        {
            "X": [TrackPull(1, "A", "Ape", R), TrackPull(2, "A", "Bee", R)],
            "Y": [TrackPull(1, "A", "Bee", R)],
            "Z": [TrackPull(1, "A", "Cow", R)],
        },
        rerolls={"X": [TrackPull(2, "A", "Rat", R, steps=1)]},
    )
    option = _plan({"Bee"}, (_single(0, "X", "Ape", R), _single(2, "X", "Bee", R)), 2)
    shared, _gshared = plan_shared(option, graphs, {})
    assert shared == {"Z": {0}}


def _guaranteed_multi_fixture(y_uber="Mecha"):
    graphs = build_graphs(
        {
            "X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Rover Cat", R)],
            "Y": [TrackPull(1, "A", "Nymph Cat", R), TrackPull(2, "A", "Delinquent Cat", R)],
        },
        {"X": [TrackPull(1, "A", "Mecha", U)], "Y": [TrackPull(1, "A", y_uber, U)]},
    )
    move = Leg(
        "X",
        "3-roll (guaranteed)",
        450,
        (
            Pull(0, "X", "Pogo", R),
            Pull(2, "X", "Rover Cat", R),
            Pull(0, "X", "Mecha", U, guaranteed=True),
        ),
    )
    return graphs, _plan({"Mecha"}, (move,), catfood=3)


def test_plan_shared_multi_needs_only_the_walk_and_the_targeted_uber():
    graphs, option = _guaranteed_multi_fixture()
    multis = {"X": [Multi(3, 450)], "Y": [Multi(3, 450)]}
    shared, gshared = plan_shared(option, graphs, {}, multis)
    assert shared == {"Y": {0, 2}}
    assert gshared == {"Y": {0}}


def test_plan_shared_multi_not_on_offer_elsewhere_is_not_interchangeable():
    graphs, option = _guaranteed_multi_fixture()
    assert plan_shared(option, graphs, {}, {"X": [Multi(3, 450)]}) == ({}, {})


def test_plan_shared_multi_missing_the_targeted_uber_is_not_interchangeable():
    graphs, option = _guaranteed_multi_fixture(y_uber="Kasli")
    multis = {"X": [Multi(3, 450)], "Y": [Multi(3, 450)]}
    assert plan_shared(option, graphs, {}, multis) == ({}, {})


def test_plan_shared_never_offers_a_capped_ticket_gacha_as_an_alternative():
    pulls = [TrackPull(1, "A", "Pogo", R)]
    graphs = build_graphs({"X": list(pulls), "Platinum Capsules": list(pulls)})
    option = _plan({"Pogo"}, (_single(0, "X", "Pogo", R),), 1)
    shared, _gshared = plan_shared(option, graphs, {}, exclude={"Platinum Capsules": 0})
    assert shared == {}


def test_plan_shared_keys_marks_by_the_representative_banner():
    pulls = [TrackPull(1, "A", "Pogo", R)]
    graphs = build_graphs({"X": list(pulls), "Y": list(pulls), "Z": list(pulls)})
    equivalents = {"Y": ["Y", "Z"], "Z": ["Y", "Z"]}
    option = _plan({"Pogo"}, (_single(0, "X", "Pogo", R),), 1)
    shared, _gshared = plan_shared(option, graphs, equivalents)
    assert shared == {"Y": {0}}


def test_plan_summary_shortens_leg_names_to_display_titles():
    leg = _single(0, "New unit Bahamut added!", "Bahamut", U)
    option = _plan({"Bahamut"}, (leg,), 1)
    summary = plan_summary([option], {}, titles={"New unit Bahamut added!": "The Dynamites"})
    assert summary[0]["legs"][0]["names"] == ["The Dynamites"]


def test_build_tracks_marks_an_interchangeable_entry():
    banner_pulls = {
        "X": [TrackPull(1, "A", "Pogo", R)],
        "Y": [TrackPull(1, "A", "Pogo", R)],
    }
    marks = TrackMarks(path={"X": {0}}, shared={"Y": {0}})
    track = build_tracks(banner_pulls, {}, {}, marks=marks)
    cell = track["rows"][0]["a"]
    assert [(e["on_path"], e["shared"]) for e in cell] == [(True, False), (False, True)]
    assert track["has_shared"] is True


def test_build_tracks_guaranteed_entry_can_be_shared():
    banner_pulls = {
        "X": [TrackPull(1, "A", "Shaman Cat", R)],
        "Y": [TrackPull(1, "A", "Shaman Cat", R)],
    }
    guaranteed = {"X": [TrackPull(1, "A", "Mecha", U)], "Y": [TrackPull(1, "A", "Mecha", U)]}
    marks = TrackMarks(gpath={"X": {0}}, gshared={"Y": {0}})
    track = build_tracks(banner_pulls, {}, {}, marks=marks, guaranteed=guaranteed)
    cell = track["rows"][0]["ga"]
    assert [(e["on_path"], e["shared"]) for e in cell] == [(True, False), (False, True)]


def test_build_tracks_without_marks_has_no_shared():
    track = build_tracks({"X": [TrackPull(1, "A", "Pogo", R)]}, {}, {})
    assert track["has_shared"] is False
    assert track["rows"][0]["a"][0]["shared"] is False


def test_build_tracks_legend_uses_display_titles():
    banner_pulls = {"New unit Bahamut added!": [TrackPull(1, "A", "Bahamut", U)]}
    track = build_tracks(banner_pulls, {}, {}, titles={"New unit Bahamut added!": "The Dynamites"})
    assert track["legend"][0]["names"] == ["The Dynamites"]


def test_subset_solutions_marks_interchangeable_steps_on_the_track():
    pulls = {
        "X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Bahamut", U)],
        "Y": [TrackPull(1, "A", "Rover Cat", R), TrackPull(2, "A", "Kasli", U)],
    }
    (solution,) = subset_solutions(pulls, {}, {}, {"Bahamut"}, tickets=2, catfood=0)
    cells = solution["track"]["rows"][0]["a"] + solution["track"]["rows"][1]["a"]
    assert [(e["cat"], e["shared"]) for e in cells] == [
        ("Pogo", False),
        ("Rover Cat", True),
        ("Bahamut", False),
        ("Kasli", False),
    ]


def test_subset_solutions_remembers_the_plans_final_pull():
    pulls = {"X": [TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Bahamut", U, seed=8)]}
    (solution,) = subset_solutions(pulls, {}, {}, {"Bahamut"}, tickets=2, catfood=0)
    assert (solution["seed_after"], solution["last_cat"]) == (8, "Bahamut")


def test_subset_solutions_start_dupe_memory_reaches_the_search():
    pulls = {"X": [TrackPull(1, "A", "Pogo", R)]}
    rerolls = {"X": [TrackPull(1, "A", "Jurassic Cat", R, steps=1)]}
    (solution,) = subset_solutions(
        pulls, rerolls, {}, {"Jurassic Cat"}, tickets=1, catfood=0, last_cat="Pogo"
    )
    assert solution["found"] is True and solution["last_cat"] == "Jurassic Cat"


@pytest.mark.parametrize(
    "rarity, title",
    [
        ("Normal", "Cat_(Normal_Cat)"),
        ("Special", "Cat_(Special_Cat)"),
        ("Rare", "Cat_(Rare_Cat)"),
        ("Super Rare", "Cat_(Super_Rare_Cat)"),
        ("Uber Super Rare", "Cat_(Uber_Rare_Cat)"),
        ("Legend Rare", "Cat_(Legend_Rare_Cat)"),
    ],
)
def test_wiki_url_titles_a_page_by_the_wikis_own_rarity_label(rarity, title):
    assert wiki_url("Cat", rarity) == WIKI_BASE + title


def test_wiki_url_underscores_the_spaces_in_a_multiword_name():
    assert wiki_url("Bahamut Cat", "Uber Super Rare") == WIKI_BASE + "Bahamut_Cat_(Uber_Rare_Cat)"


def test_wiki_url_keeps_an_apostrophe_literal():
    assert wiki_url("D'arktanyan", "Uber Super Rare") == WIKI_BASE + "D'arktanyan_(Uber_Rare_Cat)"


def test_wiki_url_falls_back_to_the_bare_name_for_an_unknown_rarity():
    assert wiki_url("Doge", "") == WIKI_BASE + "Doge"
