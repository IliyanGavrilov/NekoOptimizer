import pytest

from planner.models import Cat, Seed


@pytest.mark.django_db
def test_wishlist_excludes_owned():
    Cat.objects.create(name="Bahamut", wanted=True)
    Cat.objects.create(name="Kasli", wanted=True, owned=True)
    assert list(Cat.objects.wishlist().values_list("name", flat=True)) == ["Bahamut"]


@pytest.mark.django_db
def test_unowned_excludes_owned():
    Cat.objects.create(name="Cat")
    Cat.objects.create(name="Bahamut", owned=True)
    assert list(Cat.objects.unowned().values_list("name", flat=True)) == ["Cat"]


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
