import pytest

from neko.gamedata import load_cannons, load_evolve, load_talents
from planner.models import CannonPlan, EvolvePlan, TalentPlan, Unit
from planner.services import (
    cannon_panel,
    evolve_panel,
    part_cost,
    plannable_form,
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
def test_evolve_add_defaults_to_the_true_form(client):
    unit = _unit(_TF_ONLY)
    client.post("/materials/evolve/", {"unit_id": unit.unit_id})
    plan = EvolvePlan.objects.get(unit=unit)
    assert (plan.tf, plan.uf) == (True, False)


@pytest.mark.django_db
def test_evolve_unchecking_the_last_form_removes_the_plan(client):
    unit = _unit(_TF_ONLY)
    EvolvePlan.objects.create(unit=unit, tf=True)
    client.post("/materials/evolve/", {"unit_id": unit.unit_id, "form": "tf", "on": "0"})
    assert not EvolvePlan.objects.exists()


@pytest.mark.django_db
def test_evolve_totals_sum_the_checked_forms(client):
    unit = _unit(_TF_AND_UF)
    EvolvePlan.objects.create(unit=unit, tf=True, uf=True)
    cost = load_evolve()["units"][str(_TF_AND_UF)]
    expected = sum(count for form in (cost["tf"], cost["uf"]) for _, count in form["items"])
    assert sum(count for count, _ in evolve_panel()["totals"]) == expected


@pytest.mark.django_db
def test_talent_add_plans_every_slot(client):
    unit = _unit(_TALENTED)
    client.post("/materials/talent/", {"unit_id": unit.unit_id})
    slots = load_talents()["units"][str(_TALENTED)]
    assert TalentPlan.objects.filter(unit=unit).count() == len(slots)


@pytest.mark.django_db
def test_talent_remove_clears_the_unit(client):
    unit = _unit(_TALENTED)
    TalentPlan.objects.create(unit=unit, slot=0)
    TalentPlan.objects.create(unit=unit, slot=1)
    client.post("/materials/talent/", {"unit_id": unit.unit_id, "remove": "1"})
    assert not TalentPlan.objects.exists()


@pytest.mark.django_db
def test_talent_toggle_rejects_a_slot_the_unit_lacks(client):
    unit = _unit(_TALENTED)
    response = client.post("/materials/talent/", {"unit_id": unit.unit_id, "slot": "99", "on": "1"})
    assert response.status_code == 400 and not TalentPlan.objects.exists()


@pytest.mark.django_db
def test_toggles_reject_unknown_units(client):
    assert client.post("/materials/evolve/", {"unit_id": "9999"}).status_code == 400


@pytest.mark.django_db
def test_materials_page_lists_planned_units(client):
    unit = _unit(_TF_ONLY, "Valkyrie Cat")
    EvolvePlan.objects.create(unit=unit, tf=True)
    assert unit.name.encode() in client.get("/materials/").content


_PART = {
    "construction": [[12, 1, 5, 0, 0, 0, 0, 0, 0, 0]],
    "levels": [[24, 2, 9, 0, 0, 0, 0, 0, 0, 0]],
}


def test_part_cost_from_level_zero_includes_construction():
    assert part_cost(_PART, 0, 1) == _PART["construction"] + _PART["levels"]


def test_part_cost_from_a_built_part_skips_construction():
    assert part_cost(_PART, 1, 1) == [] and part_cost({**_PART, "levels": [[1], [2]]}, 1, 2) == [
        [2]
    ]


@pytest.mark.django_db
def test_cannon_add_defaults_every_part_to_max(client):
    client.post("/materials/cannon/", {"cannon_id": _SLOW_BEAM})
    plan = CannonPlan.objects.get(cannon_id=_SLOW_BEAM)
    parts = next(c for c in load_cannons()["cannons"] if c["id"] == _SLOW_BEAM)["parts"]
    goals = (plan.cannon_goal, plan.base_goal, plan.deco_goal)
    assert goals == tuple(len(parts[key]["levels"]) for key in ("cannon", "base", "deco"))
    assert (plan.cannon_now, plan.base_now, plan.deco_now) == (0, 0, 0)


@pytest.mark.django_db
def test_cannon_raising_now_above_goal_drags_goal_along(client):
    CannonPlan.objects.create(cannon_id=_SLOW_BEAM, cannon_goal=5)
    client.post(
        "/materials/cannon/",
        {"cannon_id": _SLOW_BEAM, "part": "cannon", "bound": "now", "level": "7"},
    )
    plan = CannonPlan.objects.get(cannon_id=_SLOW_BEAM)
    assert (plan.cannon_now, plan.cannon_goal) == (7, 7)


@pytest.mark.django_db
def test_cannon_toggle_rejects_a_part_the_cannon_lacks(client):
    CannonPlan.objects.create(cannon_id=_BASE_CANNON)
    response = client.post(
        "/materials/cannon/",
        {"cannon_id": _BASE_CANNON, "part": "base", "bound": "goal", "level": "1"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_cannon_toggle_rejects_unknown_cannons(client):
    assert client.post("/materials/cannon/", {"cannon_id": "99"}).status_code == 400


@pytest.mark.django_db
def test_cannon_remove_clears_the_plan(client):
    CannonPlan.objects.create(cannon_id=_SLOW_BEAM)
    client.post("/materials/cannon/", {"cannon_id": _SLOW_BEAM, "remove": "1"})
    assert not CannonPlan.objects.exists()


@pytest.mark.django_db
def test_cannon_totals_sum_materials_engineers_and_hours(client):
    CannonPlan.objects.create(cannon_id=_SLOW_BEAM, base_goal=20)
    levels = next(c for c in load_cannons()["cannons"] if c["id"] == _SLOW_BEAM)["parts"]["base"][
        "levels"
    ]
    panel = cannon_panel()
    expected = sum(count for row in levels for count in row[1:])
    assert sum(count for count, _ in panel["totals"]) == expected
    assert panel["time"] == f"{sum(row[0] for row in levels):,}h"


@pytest.mark.django_db
def test_materials_page_lists_planned_cannons(client):
    CannonPlan.objects.create(cannon_id=_SLOW_BEAM, cannon_goal=30)
    assert b"Slow Beam" in client.get("/materials/").content
