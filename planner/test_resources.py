import pytest

from neko.gamedata import load_cannons, load_evolve, load_talents
from planner.models import CannonPlan, Profile, TalentPlan, Unit, UnitPlan
from planner.services import (
    EVOLVE_FAMILIES,
    part_cost,
    plannable_form,
    resources_board,
    talent_label,
    talent_np,
)

# Stable committed-data anchors: unit 16 has a True Form cost only, unit 59 has both
# True and Ultra Form costs, unit 9 has talents. Cannon 0 (Enhance Base) has no
# foundation/style parts; cannon 1 is the Slow Beam.
_TF_ONLY, _TF_AND_UF, _TALENTED = 16, 59, 9
_BASE_CANNON, _SLOW_BEAM = 0, 1


def _unit(unit_id, name="Some Cat"):
    return Unit.objects.create(unit_id=unit_id, name=f"{name} {unit_id}")


def _card(profile, unit_id):
    cards = resources_board(profile)["cats"]
    return next(card for card in cards if card["unit"].unit_id == unit_id)


def test_talent_label_prefers_the_quoted_ability_name():
    assert talent_label('Gain the "Weaken" ability.<br>Level up!') == "Weaken"


def test_talent_label_falls_back_to_the_first_line_without_markup():
    assert talent_label("Upgrade <color=1>Attack Power</color>.<br>More text") == (
        "Upgrade Attack Power"
    )


def test_talent_np_sums_the_curve_up_to_max_level():
    assert talent_np({"curve": 1, "max": 3}, {"1": [25, 5, 5, 5]}) == 35


def test_talent_np_without_a_curve_is_free():
    assert talent_np({"curve": 99, "max": 10}, {"1": [25]}) == 0


def test_plannable_form_drops_costless_and_missing_forms():
    cost = {"tf": {"level": 30, "xp": 0, "items": []}, "uf": None}
    assert plannable_form(cost, "tf") is None and plannable_form(cost, "uf") is None


@pytest.mark.django_db
def test_adding_a_cat_picks_nothing_for_you(client):
    unit = _unit(_TF_AND_UF)
    client.post("/resources/cat/", {"unit_id": unit.unit_id})
    plan = UnitPlan.objects.get(unit=unit)
    assert (plan.tf, plan.uf) == (False, False)


@pytest.mark.django_db
def test_a_cat_stays_on_the_list_with_everything_unticked(client, profile):
    unit = _unit(_TF_ONLY)
    UnitPlan.objects.create(profile=profile, unit=unit, tf=True)
    client.post("/resources/cat/", {"unit_id": unit.unit_id, "form": "tf", "on": "0"})
    assert UnitPlan.objects.filter(unit=unit, tf=False).exists()


@pytest.mark.django_db
def test_maxing_a_cat_ticks_every_evolution_and_talent(client, profile):
    unit = _unit(_TALENTED)
    client.post("/resources/cat/", {"unit_id": unit.unit_id, "all": "1", "on": "1"})
    slots = load_talents()["units"][str(_TALENTED)]
    assert TalentPlan.objects.filter(unit=unit).count() == len(slots)
    assert _card(profile, _TALENTED)["maxed"]


@pytest.mark.django_db
def test_clearing_a_cat_unticks_it_but_keeps_it_listed(client, profile):
    unit = _unit(_TALENTED)
    TalentPlan.objects.create(profile=profile, unit=unit, slot=0)
    client.post("/resources/cat/", {"unit_id": unit.unit_id, "all": "1", "on": "0"})
    assert not TalentPlan.objects.exists()
    assert UnitPlan.objects.filter(unit=unit).exists()


@pytest.mark.django_db
def test_removing_a_cat_drops_its_talents_too(client, profile):
    unit = _unit(_TALENTED)
    UnitPlan.objects.create(profile=profile, unit=unit)
    TalentPlan.objects.create(profile=profile, unit=unit, slot=0)
    client.post("/resources/cat/", {"unit_id": unit.unit_id, "remove": "1"})
    assert not UnitPlan.objects.exists() and not TalentPlan.objects.exists()


@pytest.mark.django_db
def test_cat_toggle_rejects_a_slot_the_unit_lacks(client):
    unit = _unit(_TALENTED)
    response = client.post("/resources/cat/", {"unit_id": unit.unit_id, "slot": "99", "on": "1"})
    assert response.status_code == 400 and not TalentPlan.objects.exists()


@pytest.mark.django_db
def test_cat_toggle_rejects_unknown_units(client):
    assert client.post("/resources/cat/", {"unit_id": "9999"}).status_code == 400


@pytest.mark.django_db
def test_a_cat_card_costs_only_what_is_ticked(profile):
    unit = _unit(_TF_AND_UF)
    UnitPlan.objects.create(profile=profile, unit=unit, tf=True, uf=True)
    cost = load_evolve()["units"][str(_TF_AND_UF)]
    expected = sum(count for form in (cost["tf"], cost["uf"]) for _, count in form["items"])
    assert sum(item["count"] for item in _card(profile, _TF_AND_UF)["cost"]) == expected


@pytest.mark.django_db
def test_the_overview_keeps_the_two_grinds_in_their_own_tables(profile):
    UnitPlan.objects.create(profile=profile, unit=_unit(_TF_ONLY), tf=True)
    CannonPlan.objects.create(profile=profile, cannon_id=_SLOW_BEAM)
    board = resources_board(profile)
    counted = {"evolve_grid": board["cats"], "build_grid": board["base"]}
    for key, cards in counted.items():
        gridded = sum(cell["count"] for row in board[key]["rows"] for cell in row["cells"] if cell)
        assert gridded == sum(card["spend"].total() for card in cards)


@pytest.mark.django_db
def test_a_family_with_nothing_left_stays_out_of_the_grid(profile):
    UnitPlan.objects.create(profile=profile, unit=_unit(_TF_ONLY), tf=True)
    labels = [row["label"] for row in resources_board(profile)["evolve_grid"]["rows"]]
    assert labels and labels != [label for label, _ in EVOLVE_FAMILIES]


@pytest.mark.django_db
def test_every_grid_row_keeps_a_cell_per_kind(profile):
    UnitPlan.objects.create(profile=profile, unit=_unit(_TF_ONLY), tf=True)
    grid = resources_board(profile)["evolve_grid"]
    assert all(len(row["cells"]) == len(grid["kinds"]) for row in grid["rows"])


_PART = {
    "construction": [[12, 1, 5, 0, 0, 0, 0, 0, 0, 0]],
    "levels": [[24, 2, 9, 0, 0, 0, 0, 0, 0, 0]],
}


def test_part_cost_from_level_zero_includes_construction():
    assert part_cost(_PART, 0) == _PART["construction"] + _PART["levels"]


def test_part_cost_from_a_built_part_skips_construction():
    assert part_cost({**_PART, "levels": [[1], [2]]}, 1) == [[2]]


def test_part_cost_of_a_maxed_part_is_nothing():
    assert part_cost(_PART, 1) == []


@pytest.mark.django_db
def test_adding_a_base_upgrade_starts_at_the_cannon_alone(client):
    client.post("/resources/base/", {"cannon_id": _SLOW_BEAM})
    plan = CannonPlan.objects.get(cannon_id=_SLOW_BEAM)
    assert (plan.cannon_now, plan.base_now, plan.deco_now) == (0, 0, 0)
    assert (plan.base_on, plan.deco_on) == (False, False)


@pytest.mark.django_db
def test_the_development_switch_toggles_off_again(client):
    client.post("/resources/base/", {"cannon_id": _SLOW_BEAM})
    client.post("/resources/base/", {"cannon_id": _SLOW_BEAM})
    assert not CannonPlan.objects.exists()


@pytest.mark.django_db
def test_an_addon_costs_nothing_until_it_is_switched_on(client, profile):
    parts = next(c for c in load_cannons()["cannons"] if c["id"] == _SLOW_BEAM)["parts"]
    CannonPlan.objects.create(
        profile=profile, cannon_id=_SLOW_BEAM, cannon_now=len(parts["cannon"]["levels"])
    )
    assert resources_board(profile)["base"][0]["spend"].total() == 0
    client.post("/resources/base/", {"cannon_id": _SLOW_BEAM, "part": "deco", "on": "1"})
    assert resources_board(profile)["base"][0]["spend"].total() > 0


@pytest.mark.django_db
def test_the_cannon_itself_cannot_be_switched_off(client):
    response = client.post(
        "/resources/base/", {"cannon_id": _SLOW_BEAM, "part": "cannon", "on": "0"}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_setting_a_part_level_tracks_the_upgrade(client):
    client.post("/resources/base/", {"cannon_id": _SLOW_BEAM, "part": "deco", "level": "7"})
    assert CannonPlan.objects.get(cannon_id=_SLOW_BEAM).deco_now == 7


@pytest.mark.django_db
def test_base_toggle_rejects_a_part_the_cannon_lacks(client):
    response = client.post(
        "/resources/base/", {"cannon_id": _BASE_CANNON, "part": "base", "level": "1"}
    )
    assert response.status_code == 400 and not CannonPlan.objects.exists()


@pytest.mark.django_db
def test_base_toggle_rejects_a_level_past_the_cap(client):
    response = client.post(
        "/resources/base/", {"cannon_id": _SLOW_BEAM, "part": "deco", "level": "21"}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_base_toggle_rejects_unknown_cannons(client):
    assert client.post("/resources/base/", {"cannon_id": "99"}).status_code == 400


@pytest.mark.django_db
def test_removing_a_base_upgrade_clears_the_plan(client, profile):
    CannonPlan.objects.create(profile=profile, cannon_id=_SLOW_BEAM, cannon_now=4)
    client.post("/resources/base/", {"cannon_id": _SLOW_BEAM, "remove": "1"})
    assert not CannonPlan.objects.exists()


@pytest.mark.django_db
def test_a_base_card_costs_only_the_levels_left_to_max(profile):
    parts = next(c for c in load_cannons()["cannons"] if c["id"] == _SLOW_BEAM)["parts"]
    CannonPlan.objects.create(
        profile=profile,
        cannon_id=_SLOW_BEAM,
        cannon_now=len(parts["cannon"]["levels"]),
        base_now=len(parts["base"]["levels"]),
        deco_now=len(parts["deco"]["levels"]) - 1,
        base_on=True,
        deco_on=True,
    )
    card = resources_board(profile)["base"][0]
    time, crew, *materials = parts["deco"]["levels"][-1]
    assert [part["left"] for part in card["parts"]] == [0, 0, 1]
    assert card["hours"] == time
    assert card["spend"].total() == sum(materials)


@pytest.mark.django_db
def test_engineers_are_the_most_one_level_needs_not_the_sum(profile):
    parts = next(c for c in load_cannons()["cannons"] if c["id"] == _SLOW_BEAM)["parts"]
    CannonPlan.objects.create(profile=profile, cannon_id=_SLOW_BEAM)
    rows = parts["cannon"]["construction"] + parts["cannon"]["levels"]
    assert resources_board(profile)["engineers"] == max(row[1] for row in rows)


@pytest.mark.django_db
def test_the_page_shows_a_card_only_once_you_add_something(client, profile):
    # The names all ship in the pickers' catalogues; a level picker means a real card.
    assert b'data-part="deco"' not in client.get("/resources/").content
    CannonPlan.objects.create(profile=profile, cannon_id=_SLOW_BEAM)
    assert b'data-part="deco"' in client.get("/resources/").content


@pytest.mark.django_db
def test_the_board_shows_only_the_visitors_own_plans(profile):
    CannonPlan.objects.create(profile=Profile.objects.create(), cannon_id=_SLOW_BEAM)
    assert resources_board(profile)["base"] == []


@pytest.mark.django_db
def test_a_first_visit_sees_an_empty_board():
    assert resources_board(Profile())["cats"] == []
