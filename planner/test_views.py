from itertools import count

import pytest

from neko.models import BannerRolls, Rarity, TrackPull
from neko.rng import backtrack
from neko.roller import DEFAULT_COUNT, RollResult
from neko.search import Multi
from planner.forms import MAX_FUTURE_UBERS, MAX_TRACK_LENGTH
from planner.models import Banner, Cat, Seed, Unit

R = Rarity.RARE
U = Rarity.UBER_SUPER_RARE

_ids = count(1)


def cat_with_unit(name, owned=False, wanted=False):
    unit = Unit.objects.create(unit_id=next(_ids), name=name, owned=owned, wanted=wanted)
    return Cat.objects.create(name=name, unit=unit)


def returns(result):
    """A fetch double that ignores its args and hands back a prebuilt RollResult."""

    def _fetch(seed, count=100, last_cat="", simulate_guaranteed=0, future_ubers=None):
        return result

    return _fetch


def fixed_rolls(rolls):
    return returns(RollResult({"x": rolls}, {}))


def fixed_banners(*pulls):
    return fixed_rolls(BannerRolls(list(pulls), []))


@pytest.mark.django_db
def test_get_shows_form(client):
    assert b"<form" in client.get("/").content


@pytest.mark.django_db
def test_targets_grouped_by_banner(client):
    banner = Banner.objects.create(name="Epicfest")
    Cat.objects.create(name="Bahamut").banners.add(banner)
    assert b"Epicfest" in client.get("/").content


@pytest.mark.django_db
def test_post_renders_plan(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_post_persists_seed(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert Seed.current() == 7


@pytest.mark.django_db
def test_use_wishlist_searches_wanted_cats(client, monkeypatch):
    cat_with_unit("Bahamut", wanted=True)
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "use_wishlist": "on"})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_guaranteed_config_reaches_target(client, monkeypatch):
    cat = Cat.objects.create(name="Target")
    result = RollResult(
        {"x": BannerRolls([TrackPull(1, "A", "Filler", U)], [TrackPull(2, "A", "Target", U)])},
        {"x": [Multi(rolls=2, cost=300)]},
    )
    monkeypatch.setattr("planner.views.fetch_banners", returns(result))
    response = client.post("/plan/", {"seed": 7, "tickets": 0, "catfood": 300, "targets": [cat.pk]})
    assert b"Target" in response.content


@pytest.mark.django_db
def test_selected_banners_use_chosen_rolls(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    called = {}

    def fake_for_banners(
        seed, names, count=100, last_cat="", simulate_guaranteed=0, future_ubers=None
    ):
        called["names"] = list(names)
        return RollResult({"Pick": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_for_banners", fake_for_banners)
    monkeypatch.setattr("planner.views.fetch_banners", fixed_banners())
    client.post(
        "/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk], "banners": ["Pick"]}
    )
    assert called["names"] == ["Pick"]


@pytest.mark.django_db
def test_platinum_legend_cap_zero_excludes_the_banner(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    result = RollResult(
        {"Platinum Capsules": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {}
    )
    monkeypatch.setattr("planner.views.fetch_banners", returns(result))
    response = client.post(
        "/plan/",
        {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk], "platinum_legend_cap": 0},
    )
    assert b"Not found" in response.content


@pytest.mark.django_db
def test_platinum_legend_allowed_by_default(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    result = RollResult(
        {"Platinum Capsules": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {}
    )
    monkeypatch.setattr("planner.views.fetch_banners", returns(result))
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_explore_mode_funds_single_pulls_with_tickets(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners",
        fixed_banners(TrackPull(1, "A", "Filler", R), TrackPull(2, "A", "Bahamut", U)),
    )
    response = client.post(
        "/plan/", {"seed": 7, "tickets": 0, "catfood": 0, "targets": [cat.pk], "explore": "on"}
    )
    assert b"2 tickets" in response.content


@pytest.mark.django_db
def test_multiple_targets_list_every_subset(client, monkeypatch):
    a = Cat.objects.create(name="Aaa")
    b = Cat.objects.create(name="Bbb")
    monkeypatch.setattr(
        "planner.views.fetch_banners",
        fixed_banners(TrackPull(1, "A", "Aaa", U), TrackPull(2, "A", "Bbb", U)),
    )
    response = client.post(
        "/plan/", {"seed": 7, "tickets": 5, "catfood": 0, "targets": [a.pk, b.pk]}
    )
    html = response.json()["solutions_html"]
    assert html.count('<details class="solution"') == 3
    assert "Aaa, Bbb" in html


@pytest.mark.django_db
def test_unreachable_subset_is_listed_not_found(client, monkeypatch):
    a = Cat.objects.create(name="Aaa")
    b = Cat.objects.create(name="Bbb")
    monkeypatch.setattr("planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Aaa", U)))
    response = client.post(
        "/plan/", {"seed": 7, "tickets": 5, "catfood": 0, "targets": [a.pk, b.pk]}
    )
    html = response.json()["solutions_html"]
    assert "Not found" in html


@pytest.mark.django_db
def test_explore_mode_rolls_to_the_horizon(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    seen = {}

    def fake(seed, count=100, last_cat="", simulate_guaranteed=0, future_ubers=None):
        seen["count"] = count
        return RollResult({"x": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    data = {"seed": 7, "tickets": 0, "catfood": 0, "targets": [cat.pk]}
    client.post("/plan/", {**data, "explore": "on", "horizon": 500})
    assert seen["count"] == 500


@pytest.mark.django_db
def test_owned_cats_are_still_targetable(client):
    cat_with_unit("Bahamut", owned=True).banners.add(Banner.objects.create(name="Epic"))
    assert b"Bahamut" in client.get("/").content


@pytest.mark.django_db
def test_seed_field_starts_empty(client):
    Seed.store(42)
    assert b'name="seed" value="42"' not in client.get("/").content


@pytest.mark.django_db
def test_apply_plan_owns_cats_and_clears_wishlist(client):
    cat = cat_with_unit("Bahamut", owned=False, wanted=True)
    client.post("/apply/", {"cats": ["Bahamut"]})
    cat.refresh_from_db()
    assert (cat.owned, cat.wanted) == (True, False)


@pytest.mark.django_db
def test_apply_plan_advances_the_stored_seed(client):
    Seed.store(7)
    client.post("/apply/", {"cats": ["Bahamut"], "seed_after": 12345})
    assert Seed.current() == 12345


@pytest.mark.django_db
def test_apply_plan_without_a_seed_after_keeps_the_stored_seed(client):
    Seed.store(7)
    client.post("/apply/", {"cats": ["Bahamut"]})
    assert Seed.current() == 7


@pytest.mark.django_db
def test_requires_targets_or_wishlist(client):
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0})
    assert response.status_code == 400


@pytest.mark.django_db
def test_negative_resources_rejected(client):
    cat = Cat.objects.create(name="Bahamut")
    response = client.post("/plan/", {"seed": 7, "tickets": -1, "catfood": 0, "targets": [cat.pk]})
    assert response.status_code == 400


@pytest.mark.django_db
def test_blank_budget_is_treated_as_zero(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post(
        "/plan/", {"seed": 7, "tickets": "", "catfood": "", "targets": [cat.pk], "explore": "on"}
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_tracks_endpoint_lists_the_rolls(client, monkeypatch):
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post("/tracks/", {"seed": 7})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_tracks_endpoint_tags_cells_with_the_unit_id_for_icons(client, monkeypatch):
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    Unit.objects.create(unit_id=25, name="Bahamut")
    response = client.post("/tracks/", {"seed": 7})
    assert b'data-uid="25"' in response.content


@pytest.mark.django_db
def test_tracks_endpoint_blank_seed_renders_nothing(client):
    assert client.post("/tracks/", {}).content == b""


@pytest.mark.django_db
def test_planner_ships_the_past_group_as_a_lazy_shell(client):
    html = client.get("/").content
    assert b'id="pastGroup"' in html
    assert html.count(b"banner-include") < 100


@pytest.mark.django_db
def test_picker_past_serves_the_past_rows(client):
    html = client.get("/picker/past/").content
    assert html.count(b"banner-include") > 1000


@pytest.mark.django_db
def test_tracks_endpoint_renders_the_guaranteed_column(client, monkeypatch):
    rolls = BannerRolls(
        [TrackPull(1, "A", "Shaman Cat", R)], [TrackPull(1, "A", "Trixi the Merc", U)]
    )
    monkeypatch.setattr("planner.views.fetch_banners", fixed_rolls(rolls))
    response = client.post("/tracks/", {"seed": 7})
    assert b"Guaranteed" in response.content
    assert b"Trixi the Merc" in response.content


@pytest.mark.django_db
def test_tracks_endpoint_hides_the_guaranteed_column_without_a_guarantee(client, monkeypatch):
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    assert b"Guaranteed" not in client.post("/tracks/", {"seed": 7}).content


@pytest.mark.django_db
def test_tracks_endpoint_renders_a_dice_per_branch_of_a_dupe_cell(client, monkeypatch):
    rolls = BannerRolls(
        [TrackPull(1, "A", "Pogo", R, seed=3), TrackPull(2, "A", "Pogo", R, seed=5)],
        [],
        [TrackPull(2, "A", "Jurassic Cat", R, seed=9, steps=1)],
    )
    monkeypatch.setattr("planner.views.fetch_banners", fixed_rolls(rolls))
    html = client.post("/tracks/", {"seed": 7}).content.decode()
    assert "if dupe:" in html
    assert 'data-seed="9"' in html
    assert 'data-seed="5"' in html
    assert 'data-cat="Pogo"' in html


@pytest.mark.django_db
def test_tracks_endpoint_forwards_the_dupe_memory(client, monkeypatch):
    seen = {}

    def fake(seed, count, last_cat="", simulate_guaranteed=0, future_ubers=None):
        seen["last_cat"] = last_cat
        return RollResult({"x": BannerRolls([TrackPull(1, "A", "Pogo", R)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    client.post("/tracks/", {"seed": 7, "last_cat": "Pogo"})
    assert seen["last_cat"] == "Pogo"


@pytest.mark.django_db
def test_tracks_endpoint_uses_the_requested_track_length(client, monkeypatch):
    seen = {}

    def fake(seed, count, last_cat="", simulate_guaranteed=0, future_ubers=None):
        seen["count"] = count
        return RollResult({"x": BannerRolls([TrackPull(1, "A", "Pogo", R)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    client.post("/tracks/", {"seed": 7, "track_length": 250})
    assert seen["count"] == 250


@pytest.mark.django_db
def test_tracks_endpoint_clamps_the_track_length(client, monkeypatch):
    seen = {}

    def fake(seed, count, last_cat="", simulate_guaranteed=0, future_ubers=None):
        seen["count"] = count
        return RollResult({"x": BannerRolls([TrackPull(1, "A", "Pogo", R)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    client.post("/tracks/", {"seed": 7, "track_length": 5000})
    assert seen["count"] == MAX_TRACK_LENGTH
    client.post("/tracks/", {"seed": 7, "track_length": "junk"})
    assert seen["count"] == DEFAULT_COUNT


@pytest.mark.django_db
def test_tracks_endpoint_forwards_the_simulate_guaranteed_count(client, monkeypatch):
    seen = {}

    def fake(seed, count, last_cat="", simulate_guaranteed=0, future_ubers=None):
        seen["simulate_guaranteed"] = simulate_guaranteed
        return RollResult({"x": BannerRolls([TrackPull(1, "A", "Pogo", R)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    client.post("/tracks/", {"seed": 7})
    assert seen["simulate_guaranteed"] == 0
    client.post("/tracks/", {"seed": 7, "simulate_guaranteed": 11})
    assert seen["simulate_guaranteed"] == 11
    # A size the dropdown doesn't offer is ignored, so it can't balloon the grid.
    client.post("/tracks/", {"seed": 7, "simulate_guaranteed": 999})
    assert seen["simulate_guaranteed"] == 0


@pytest.mark.django_db
def test_tracks_endpoint_forwards_and_clamps_the_future_ubers_map(client, monkeypatch):
    seen = {}

    def fake(seed, count, last_cat="", simulate_guaranteed=0, future_ubers=None):
        seen["future_ubers"] = future_ubers
        return RollResult({"x": BannerRolls([TrackPull(1, "A", "Pogo", R)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    client.post("/tracks/", {"seed": 7})
    assert seen["future_ubers"] == {}
    client.post("/tracks/", {"seed": 7, "future_ubers": '{"x": 5}'})
    assert seen["future_ubers"] == {"x": 5}
    client.post("/tracks/", {"seed": 7, "future_ubers": '{"x": 5000}'})
    assert seen["future_ubers"] == {"x": MAX_FUTURE_UBERS}
    # Malformed JSON, non-dict payloads, junk counts and zeros all mean no padding.
    client.post("/tracks/", {"seed": 7, "future_ubers": "junk"})
    assert seen["future_ubers"] == {}
    client.post("/tracks/", {"seed": 7, "future_ubers": "[5]"})
    assert seen["future_ubers"] == {}
    client.post("/tracks/", {"seed": 7, "future_ubers": '{"x": "junk", "y": 0}'})
    assert seen["future_ubers"] == {}


@pytest.mark.django_db
def test_tracks_endpoint_renders_a_trace_click_as_plan_marks(client, monkeypatch):
    rolls = BannerRolls([TrackPull(1, "A", "Pogo", R), TrackPull(2, "A", "Kasa", U)], [])
    monkeypatch.setattr("planner.views.fetch_banners", fixed_rolls(rolls))
    # The guide's sample swatch also carries on-path, so check cell classes exactly.
    plain = client.post("/tracks/", {"seed": 7}).content.decode()
    assert 'class="entry on-path"' not in plain
    traced = client.post(
        "/tracks/", {"seed": 7, "trace_tag": "1", "trace_idx": "2"}
    ).content.decode()
    assert 'class="entry on-path"' in traced  # 1A, the walk's first step
    assert "entry on-path target" in traced  # the clicked cell wears the gold pill
    # Malformed trace params mark nothing rather than erroring.
    junk = client.post("/tracks/", {"seed": 7, "trace_tag": "x", "trace_idx": "y"})
    assert b"entry on-path target" not in junk.content


@pytest.mark.django_db
def test_tracks_endpoint_traces_a_guaranteed_column_click(client, monkeypatch):
    rolls = BannerRolls(
        [TrackPull(1, "A", "Shaman Cat", R)], [TrackPull(1, "A", "Trixi the Merc", U)]
    )
    monkeypatch.setattr("planner.views.fetch_banners", fixed_rolls(rolls))
    traced = client.post(
        "/tracks/", {"seed": 7, "trace_tag": "1", "trace_idx": "0", "trace_guaranteed": "1"}
    ).content.decode()
    # The guaranteed uber wears the gold pill; a plain (non-guaranteed) click at the same
    # cell would instead mark Shaman Cat in the normal column.
    assert "entry on-path target" in traced
    assert "Trixi the Merc" in traced


@pytest.mark.django_db
def test_tracks_endpoint_renders_a_dice_on_the_guaranteed_cell(client, monkeypatch):
    rolls = BannerRolls(
        [TrackPull(1, "A", "Shaman Cat", R)], [TrackPull(1, "A", "Trixi the Merc", U, seed=42)]
    )
    monkeypatch.setattr("planner.views.fetch_banners", fixed_rolls(rolls))
    assert b'data-seed="42"' in client.post("/tracks/", {"seed": 7}).content


@pytest.mark.django_db
def test_seed_backtrack_steps_the_seed_back_one_roll(client):
    seed = 1893568593
    assert client.post("/seed/backtrack/", {"seed": seed}).json()["seed"] == backtrack(seed)


@pytest.mark.django_db
def test_seed_backtrack_rejects_a_non_integer_seed(client):
    assert client.post("/seed/backtrack/", {"seed": "junk"}).status_code == 400


@pytest.mark.django_db
def test_unit_info_lists_a_units_forms(client):
    Unit.objects.create(
        unit_id=25, name="Bahamut", rarity="Uber Super Rare", forms=["Bahamut", "Aqua Bahamut"]
    )
    assert client.get("/unit/info/", {"name": "Bahamut"}).json()["forms"] == [
        "Bahamut",
        "Aqua Bahamut",
    ]


@pytest.mark.django_db
def test_unit_info_links_to_the_wiki_page(client):
    Unit.objects.create(unit_id=25, name="Bahamut", rarity="Uber Super Rare")
    wiki = client.get("/unit/info/", {"name": "Bahamut"}).json()["wiki"]
    assert wiki.endswith("/Bahamut_(Uber_Rare_Cat)")


@pytest.mark.django_db
def test_unit_info_reports_an_unknown_cat_as_not_found(client):
    assert client.get("/unit/info/", {"name": "Nobody"}).json() == {"found": False}


@pytest.mark.django_db
def test_unit_forms_maps_every_unit_in_one_payload(client):
    Unit.objects.create(unit_id=25, name="Bahamut", forms=["Bahamut", "Aqua Bahamut"])
    Unit.objects.create(unit_id=44, name="Kasa Jizo", forms=["Kasa Jizo"])
    assert client.get("/unit/forms/").json() == {
        "25": ["Bahamut", "Aqua Bahamut"],
        "44": ["Kasa Jizo"],
    }
