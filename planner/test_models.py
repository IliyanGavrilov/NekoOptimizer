from itertools import count

import pytest

from neko import region
from planner.models import Cat, Seed, Unit, UnitPlan

_ids = count(1)


def make_cat(name, owned=False, wanted=False):
    unit = Unit.objects.create(unit_id=next(_ids), name=name, owned=owned, wanted=wanted)
    return Cat.objects.create(name=name, unit=unit)


@pytest.mark.django_db
def test_wishlist_excludes_owned():
    make_cat("Bahamut", wanted=True)
    make_cat("Kasli", wanted=True, owned=True)
    assert list(Unit.objects.wishlist().values_list("name", flat=True)) == ["Bahamut"]


@pytest.mark.django_db
def test_seed_round_trips():
    Seed.store(123456789)
    assert Seed.current() == 123456789


@pytest.mark.django_db
def test_seed_missing_is_none():
    assert Seed.current() is None


@pytest.mark.django_db
def test_seed_store_overwrites_previous():
    Seed.store(1)
    Seed.store(2)
    assert Seed.current() == 2


@pytest.mark.django_db
def test_seed_is_kept_per_region():
    Seed.store(1)
    with region.using("jp"):
        Seed.store(2)

    assert Seed.current() == 1


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
        UnitPlan.objects.create(unit=Unit.objects.create(unit_id=1, name="ネコ"), tf=True)

    assert list(UnitPlan.objects.all()) == []
