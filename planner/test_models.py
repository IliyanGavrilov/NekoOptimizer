from itertools import count

import pytest

from planner.models import Cat, Seed, Unit

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
