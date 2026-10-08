from itertools import count

import pytest

from neko import region
from planner.models import Profile, Seed, Unit, UnitPlan

_ids = count(1)


def make_unit(name):
    return Unit.objects.create(unit_id=next(_ids), name=name)


@pytest.mark.django_db
def test_wishlist_excludes_owned():
    profile = Profile.objects.create()
    bahamut, kasli = make_unit("Bahamut"), make_unit("Kasli")
    profile.wanted.add(bahamut, kasli)
    profile.owned.add(kasli)
    assert list(profile.wishlist().values_list("name", flat=True)) == ["Bahamut"]


@pytest.mark.django_db
def test_marks_belong_to_one_profile():
    profile = Profile.objects.create()
    Profile.objects.create().owned.add(make_unit("Bahamut"))
    assert profile.marks() == (set(), set())


@pytest.mark.django_db
def test_an_unsaved_profile_has_no_marks():
    make_unit("Bahamut")
    assert Profile().marks() == (set(), set())


@pytest.mark.django_db
def test_an_unsaved_profile_has_an_empty_wishlist():
    assert not Profile().wishlist().exists()


@pytest.mark.django_db
def test_marks_are_scoped_to_the_active_region():
    profile = Profile.objects.create()
    with region.using("jp"):
        profile.owned.add(make_unit("ネコ"))

    assert not profile.units("owned").exists()


@pytest.mark.django_db
def test_seed_store_overwrites_previous():
    profile = Profile.objects.create()
    Seed.store(profile, 1)
    Seed.store(profile, 2)
    assert Seed.objects.get().value == 2


@pytest.mark.django_db
def test_seed_is_kept_per_region():
    profile = Profile.objects.create()
    Seed.store(profile, 1)
    with region.using("jp"):
        Seed.store(profile, 2)

    assert Seed.objects.get(region="en").value == 1


@pytest.mark.django_db
def test_seed_is_kept_per_profile():
    Seed.store(Profile.objects.create(), 1)
    Seed.store(Profile.objects.create(), 2)
    assert Seed.objects.count() == 2


@pytest.mark.django_db
def test_queries_see_only_the_active_regions_units():
    with region.using("jp"):
        Unit.objects.create(unit_id=1, name="ネコ")

    assert list(Unit.objects.all()) == []


@pytest.mark.django_db
def test_the_same_unit_id_lives_in_every_region():
    Unit.objects.create(unit_id=1, name="Cat")
    with region.using("jp"):
        Unit.objects.create(unit_id=1, name="ネコ")

    assert Unit.all_regions.filter(unit_id=1).count() == 2


@pytest.mark.django_db
def test_plans_are_scoped_through_the_unit_they_hang_off():
    with region.using("jp"):
        UnitPlan.objects.create(
            profile=Profile.objects.create(),
            unit=Unit.objects.create(unit_id=1, name="ネコ"),
            tf=True,
        )

    assert list(UnitPlan.objects.all()) == []


def _guide(**regions):
    return lambda: {"regions": regions}


@pytest.mark.django_db
def test_in_guide_drops_units_the_cat_guide_doesnt_list(monkeypatch):
    monkeypatch.setattr("planner.models.load_guide", _guide(en=[1]))
    Unit.objects.create(unit_id=1, name="Cat")
    Unit.objects.create(unit_id=77, name="Droid Cat")

    assert list(Unit.objects.in_guide().values_list("name", flat=True)) == ["Cat"]


@pytest.mark.django_db
def test_in_guide_keeps_every_unit_of_a_region_the_guide_cant_list_in_full(monkeypatch):
    monkeypatch.setattr("planner.models.load_guide", _guide(jp=[1]))
    with region.using("jp"):
        Unit.objects.create(unit_id=77, name="ドロイド")

        assert Unit.objects.in_guide().count() == 1


@pytest.mark.django_db
def test_in_guide_keeps_every_unit_when_the_guide_lists_none(monkeypatch):
    monkeypatch.setattr("planner.models.load_guide", _guide())
    Unit.objects.create(unit_id=77, name="Droid Cat")

    assert Unit.objects.in_guide().count() == 1
