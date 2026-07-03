from datetime import date

import pytest

from neko.graph import build_graphs
from neko.models import BannerRolls, Leg, Path, Pull, Rarity, TrackPull
from neko.subsets import SubsetPlan
from planner.models import Banner, Cat, Unit
from planner.services import (
    ADDONS_LABEL,
    REGULARS_LABEL,
    banner_titles,
    build_tracks,
    capped_banner_limits,
    collection_sections,
    cost_label,
    equivalent_banners,
    picker_groups,
    plan_highlight,
    plan_seed,
    plan_summary,
    series_names,
    set_sections,
)

U = Rarity.UBER_SUPER_RARE
R = Rarity.RARE


def test_capped_banner_limits_matches_only_platinum_and_legend():
    names = ["Platinum Capsules", "Legend Capsules", "Epicfest"]
    assert capped_banner_limits(names, 0) == {"Platinum Capsules": 0, "Legend Capsules": 0}


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
    # The fest pool mixes both sets evenly (an umbrella), so the legend homes to the
    # Dynamites' own banner and joins their named section.
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
    # Rover rides every banner; Neneko only 4 of 10 (fests and collabs skip her).
    pools = {i: [50, 60] if i <= 4 else [50] for i in range(1, 11)}
    sections = set_sections([rover, neneko], events, pools, {i: i for i in range(1, 11)})
    assert [label for label, _ in sections] == [REGULARS_LABEL, ADDONS_LABEL]
    assert dict(sections)[ADDONS_LABEL] == [("Super Rare", [neneko])]


def _fest_fixture():
    """Three fests over two exclusive fest sets, a classic set, and a fest-only legend:
    Uberfest (19) and Epicfest (27) each carry the classics plus their own set, and
    Superfest (42) carries both fest sets; Izanagi drops on Uberfest and Superfest."""
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
    # The guide's "UBER FEST" set and the fest series label the same section, respelled.
    assert ("Legend Rare", [izanagi]) in sections["UBERFEST"]
    assert ("Legend Rare", [izanagi]) in sections["SUPERFEST"]
    assert ("Legend Rare", [izanagi]) not in sections["EPICFEST"]


def test_set_sections_bundles_covered_sets_but_not_the_general_uber_pool():
    units, events, pools, series = _fest_fixture()
    sections = dict(set_sections(units, events, pools, series))
    superfest = [u.name for _, bin in sections["SUPERFEST"] for u in bin]
    # Both fest sets combine on Superfest; the classics drop on every fest, so they
    # stay under their own set only.
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
    # Each legend homes to its set's banner; Royal Fest (a mixed pool) carries them all.
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
    # Both pools carry the whole set; the smaller one is its own banner. The fest
    # series keeps its fest name.
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
    now = [(name, dates) for name, _title, dates, _ in groups["Available now"]]
    assert now == [
        ("Platinum", (date(2026, 4, 24), date(2026, 7, 10))),
        ("Trixi", (date(2026, 6, 26), date(2026, 7, 3))),
    ]
    upcoming = [(n, d) for n, _t, d, _ in groups["Upcoming"]]
    assert upcoming == [("Platinum", (date(2026, 7, 11), sentinel))]
    # both Platinum rows carry the same cats, joined by name
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
    path, targets, gpath, gtargets = plan_highlight(option, {"X": ["X", "Y"], "Y": ["X", "Y"]})
    assert (path, targets) == ({"X": {0}}, {"X": {0}})
    assert (gpath, gtargets) == ({}, {})


def test_plan_highlight_routes_guaranteed_pulls_to_the_guaranteed_column():
    # The guaranteed uber lights the guaranteed COLUMN at the multi's first roll, not the
    # track cell of some later position.
    pulls = (Pull(0, "X", "Cat", R), Pull(0, "X", "Mecha", U, guaranteed=True))
    option = SubsetPlan(frozenset({"Mecha"}), Path(pulls, 0, 3))
    path, targets, gpath, gtargets = plan_highlight(option, {})
    assert (path, targets) == ({"X": {0}}, {})
    assert (gpath, gtargets) == ({"X": {0}}, {"X": {0}})


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


def test_build_tracks_highlights_the_guaranteed_column_cell():
    # A plan that starts a guaranteed multi at 1A lights 1A's guaranteed-column cell (the
    # uber it awards); the normal track cell keeps its normal roll.
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "Trixi the Merc", U)]}
    track = build_tracks(
        banner_pulls,
        {},
        {},
        path={"X": {0}},
        guaranteed=guaranteed,
        gpath={"X": {0}},
        gtargets={"X": {0}},
    )
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
    # Banner Y runs no guarantee, so the guaranteed cell holds X's uber alone.
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
    # An empty uber pool rolls "" (godfat's id -1); the cell renders nothing for it.
    banner_pulls = {"X": [TrackPull(1, "A", "Shaman Cat", R)]}
    guaranteed = {"X": [TrackPull(1, "A", "", U)]}
    track = build_tracks(banner_pulls, {}, {}, guaranteed=guaranteed)
    assert track["rows"][0]["ga"] == []


def test_build_tracks_row_carries_the_cell_dice_seed():
    banner_pulls = {"X": [TrackPull(1, "A", "Bahamut", U, seed_before=111)]}
    assert build_tracks(banner_pulls, {}, {})["rows"][0]["a_seed"] == 111


def test_build_tracks_cell_dice_reads_any_banner_rolled_there():
    # The anchor is banner-independent (pure stream position), so a banner that wasn't
    # rolled at the cell doesn't blank its dice - another banner's pull supplies it.
    banner_pulls = {
        "X": [TrackPull(1, "A", "Pogo", R, seed_before=5)],
        "Y": [
            TrackPull(1, "A", "Kasli", U, seed_before=5),
            TrackPull(2, "A", "Pogo", R, seed_before=7),
        ],
    }
    track = build_tracks(banner_pulls, {}, {})
    assert (track["rows"][0]["a_seed"], track["rows"][1]["a_seed"]) == (5, 7)


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
